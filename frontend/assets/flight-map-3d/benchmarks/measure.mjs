/**
 * Airspace performance benchmark.
 *
 * Usage:
 *   1. npm run build && npm run preview        (terminal 1 — serves dist/build)
 *   2. python -m uvicorn main:app --port 8000  (terminal 2 — backend)
 *   3. npm run benchmark                       (terminal 3)
 *
 * Measures, per device profile (desktop + Pixel 7 emulation):
 *   - cold load:            navigation -> first `airspace:scenario-loaded`
 *   - scenario switch:      dispatch -> matching `airspace:scenario-loaded`
 *   - frame rate:           rAF sampling over 5 s after scene settle
 *   - draw calls/triangles: renderer.info via ?benchmark=1 probe
 *   - payload size:         decoded JSON bytes per scenario endpoint
 *
 * Results print to stdout as a markdown table and are saved to
 * benchmarks/results.json for the before/after report.
 */
import { chromium, devices } from 'playwright';
import { mkdirSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const PREVIEW_URL = process.env.BENCH_URL || 'http://localhost:5173';
const API_BASE = process.env.BENCH_API || 'http://localhost:8000';

const SCENARIOS = [
    'crossroads-storm',
    'storm-wall',
    'slalom',
    'in-flight-replan',
];

const PROFILES = [
    { name: 'desktop', contextOptions: { viewport: { width: 1280, height: 800 } } },
    { name: 'pixel-7', contextOptions: { ...devices['Pixel 7'] } },
];

// Collects every bridge event the page emits into window.__benchEvents,
// and exposes a dispatch helper that survives before the app boots.
const INIT_SCRIPT = `
    window.__benchEvents = [];
    window.addEventListener('message', event => {
        const data = event.data;
        if (data && typeof data === 'object' && typeof data.type === 'string'
            && data.type.startsWith('airspace:')) {
            window.__benchEvents.push({ ...data, __t: performance.now() });
        }
    });
`;

async function waitForEvent(page, type, match = () => true, timeoutMs = 30000) {
    return page.waitForFunction(
        ([eventType, isMatchSrc]) => {
            const isMatch = eval('(' + isMatchSrc + ')');
            return window.__benchEvents.some(e => e.type === eventType && isMatch(e));
        },
        [type, match.toString()],
        { timeout: timeoutMs },
    );
}

async function dispatchScenario(page, scenario) {
    await page.evaluate(id => window.airspaceBridge.dispatch({
        type: 'airspace:loadScenario', scenario: id,
    }), scenario);
}

async function measureFps(page, seconds = 5) {
    return page.evaluate(async (durationMs) => {
        return new Promise(resolve => {
            let frames = 0;
            const start = performance.now();
            const tick = () => {
                frames += 1;
                if (performance.now() - start < durationMs) {
                    requestAnimationFrame(tick);
                } else {
                    resolve(frames / ((performance.now() - start) / 1000));
                }
            };
            requestAnimationFrame(tick);
        });
    }, seconds * 1000);
}

async function measurePayload(scenario) {
    try {
        const response = await fetch(`${API_BASE}/test-scenarios/${scenario}`);
        if (!response.ok) return null;
        const text = await response.text();
        return { decoded_bytes: Buffer.byteLength(text) };
    } catch {
        return null;
    }
}

async function runProfile(browser, profile) {
    const context = await browser.newContext(profile.contextOptions);
    await context.addInitScript(INIT_SCRIPT);
    const page = await context.newPage();
    const results = { profile: profile.name, scenarios: {} };

    // --- Cold load (first paint of the default scenario) ---
    const navStart = Date.now();
    await page.goto(`${PREVIEW_URL}/?benchmark=1`, { waitUntil: 'domcontentloaded' });
    await waitForEvent(page, 'airspace:scenario-loaded');
    results.cold_load_ms = Math.round(Date.now() - navStart);

    // --- Draw calls after the scene settles ---
    await page.waitForTimeout(2500);
    results.render_info = await page.evaluate(() =>
        window.__AIRSPACE_PERFORMANCE ? window.__AIRSPACE_PERFORMANCE() : null);

    // --- Frame rate ---
    results.fps = Math.round(await measureFps(page, 5) * 10) / 10;

    // --- Scenario switches ---
    for (const scenario of SCENARIOS) {
        const start = Date.now();
        await dispatchScenario(page, scenario);
        await waitForEvent(page, 'airspace:scenario-loaded',
            e => e.scenario === scenario);
        const elapsed = Math.round(Date.now() - start);
        results.scenarios[scenario] = { switch_ms: elapsed };
        await page.waitForTimeout(400);
    }

    // --- Payload sizes (device-independent, measured once per run) ---
    if (profile === PROFILES[0]) {
        for (const scenario of SCENARIOS) {
            results.scenarios[scenario].payload = await measurePayload(scenario);
        }
    }

    await context.close();
    return results;
}

async function main() {
    console.log(`Benchmarking ${PREVIEW_URL} against ${API_BASE} …\n`);
    const browser = await chromium.launch();
    const all = [];
    for (const profile of PROFILES) {
        process.stdout.write(`  profile: ${profile.name} … `);
        all.push(await runProfile(browser, profile));
        console.log('done');
    }
    await browser.close();

    // --- Report ---
    const rows = all.map(r => {
        const info = r.render_info || {};
        const switches = Object.entries(r.scenarios)
            .map(([name, s]) => `${name}: ${s.switch_ms} ms`)
            .join(', ');
        return `| ${r.profile} | ${r.cold_load_ms} ms | ${r.fps} | ${info.calls ?? '—'} | ${info.triangles ?? '—'} | ${switches} |`;
    });

    console.log(`
## Benchmark results

| Profile | Cold load | FPS | Draw calls | Triangles | Scenario switches |
|---|---:|---:|---:|---:|---|
${rows.join('\n')}

Payload sizes (decoded JSON — verify wire gzip with:
  curl -sH 'Accept-Encoding: gzip' -o /dev/null -w '%{size_download}' \\
    ${API_BASE}/test-scenarios/storm-wall
):`);

    for (const r of all) {
        for (const [name, s] of Object.entries(r.scenarios)) {
            if (s.payload) {
                console.log(`  ${name}: ${(s.payload.decoded_bytes / 1024).toFixed(1)} KB decoded`);
            }
        }
        break; // payload measured once, on the first profile
    }

    mkdirSync(__dirname, { recursive: true });
    const outFile = join(__dirname, 'results.json');
    writeFileSync(outFile, JSON.stringify(all, null, 2));
    console.log(`\nSaved: ${outFile}`);
}

main().catch(error => {
    console.error('Benchmark failed:', error);
    process.exit(1);
});