import { gzipSync } from 'node:zlib';
import { chromium } from 'playwright';

const baseUrl = process.env.BASE_URL || 'http://127.0.0.1:5173';
const switchCount = Math.max(1, Number(process.env.SWITCH_COUNT) || 3);
const fpsDurationMs = Math.max(1000, Number(process.env.FPS_DURATION_MS) || 5000);
const switchTimeoutMs = Math.max(1000, Number(process.env.SWITCH_TIMEOUT_MS) || 20000);
const switchScenarios = (process.env.BENCHMARK_SCENARIOS || 'storm-wall,low-corridor,slalom')
  .split(',')
  .map(scenario => scenario.trim())
  .filter(Boolean);
const measurements = {
  baseUrl,
  startedAt: new Date().toISOString(),
  coldLoadMs: null,
  scenarioSwitchMs: [],
  sustainedFps: null,
  apiResponses: [],
  browserErrors: [],
};

const browser = await chromium.launch({ headless: true });

try {
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 1,
    isMobile: true,
    hasTouch: true,
  });
  const page = await context.newPage();
  const responseReadTasks = [];
  page.on('pageerror', error => measurements.browserErrors.push(error.message));
  page.on('requestfailed', request => {
    if (/localhost:8000/.test(request.url())) {
      measurements.browserErrors.push(`${request.method()} ${request.url()}: ${request.failure()?.errorText || 'request failed'}`);
    }
  });
  page.on('response', response => {
    if (!/\/test-scenarios\//.test(response.url())) return;

    responseReadTasks.push((async () => {
      try {
        const body = await response.body();
        const headers = await response.allHeaders();
        const responseEnd = response.request().timing().responseEnd;
        measurements.apiResponses.push({
          url: response.url(),
          status: response.status(),
          responseMs: responseEnd >= 0 ? Math.round(responseEnd) : null,
          payloadBytes: body.length,
          gzipBytes: gzipSync(body).length,
          wireBytes: Number(headers['content-length']) || null,
          contentEncoding: headers['content-encoding'] || null,
        });
      } catch (error) {
        measurements.browserErrors.push(`Could not read scenario response: ${error.message}`);
      }
    })());
  });

  const coldStart = performance.now();
  await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => (
    document.body.classList.contains('scene-ready')
    && document.querySelector('#optimized-distance')?.textContent !== '—'
  ), { timeout: 90000 });
  measurements.coldLoadMs = Math.round(performance.now() - coldStart);
  measurements.renderer = await page.evaluate(
    () => window.__AIRSPACE_PERFORMANCE__?.() || null,
  );

  measurements.sustainedFps = await page.evaluate(durationMs => new Promise(resolve => {
    let frames = 0;
    const started = performance.now();
    const sample = now => {
      frames += 1;
      if (now - started >= durationMs) {
        resolve(Math.round(frames * 1000 / (now - started)));
        return;
      }
      requestAnimationFrame(sample);
    };
    requestAnimationFrame(sample);
  }), fpsDurationMs);

  const selector = page.locator('#scenario-selector');
  const scenarios = await selector.locator('option').evaluateAll(options =>
    options.map(option => option.value).filter(Boolean),
  );
  const selectedScenarios = switchScenarios.slice(0, switchCount);
  const unavailable = selectedScenarios.filter(scenario => !scenarios.includes(scenario));
  if (unavailable.length > 0) {
    throw new Error(`Unknown benchmark scenario(s): ${unavailable.join(', ')}`);
  }

  for (const scenario of selectedScenarios) {
    const currentScenario = await selector.inputValue();
    if (scenario === currentScenario) {
      continue;
    }

    const started = performance.now();
    const responsePromise = page.waitForResponse(
      response => new URL(response.url()).pathname.endsWith(`/test-scenarios/${scenario}`),
      { timeout: switchTimeoutMs },
    );
    await selector.selectOption(scenario);
    try {
      await responsePromise;
    } catch (error) {
      const failures = measurements.browserErrors.join('; ') || 'no API request error was captured';
      throw new Error(`No response while switching to ${scenario}: ${failures}`, { cause: error });
    }
    await page.waitForFunction(() => {
      const status = document.querySelector('#data-status')?.textContent || '';
      return !status.startsWith('Loading ') && !status.startsWith('Checking ');
    }, { timeout: 90000 });
    measurements.scenarioSwitchMs.push(Math.round(performance.now() - started));
  }

  await Promise.all(responseReadTasks);
  measurements.finishedAt = new Date().toISOString();
  console.log(JSON.stringify(measurements, null, 2));
  if (measurements.browserErrors.length > 0) process.exitCode = 1;
} finally {
  await browser.close();
}
