import { gzipSync } from 'node:zlib';
import { chromium } from 'playwright';

const baseUrl = process.env.BASE_URL || 'http://127.0.0.1:5173/?scenario=crossroads-storm';
const apiBaseUrl = process.env.API_BASE_URL || 'http://localhost:8000';
const apiOrigin = new URL(apiBaseUrl).origin;
const switchCount = Math.max(1, Number(process.env.SWITCH_COUNT) || 3);
const fpsDurationMs = Math.max(1000, Number(process.env.FPS_DURATION_MS) || 5000);
const switchTimeoutMs = Math.max(1000, Number(process.env.SWITCH_TIMEOUT_MS) || 30000);
const requestedScenarios = (process.env.BENCHMARK_SCENARIOS || 'storm-wall,low-corridor,slalom')
  .split(',')
  .map(scenario => scenario.trim())
  .filter(Boolean)
  .slice(0, switchCount);
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
let page;

try {
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 1,
    isMobile: true,
    hasTouch: true,
  });
  page = await context.newPage();
  const responseReadTasks = [];

  await page.addInitScript(configuredApiBase => {
    if (configuredApiBase) window.AIRSPACE_API_BASE = configuredApiBase;
    window.__AIRSPACE_EVENTS__ = [];
    window.addEventListener('airspace:bridge', event => {
      window.__AIRSPACE_EVENTS__.push(event.detail);
    });
  }, apiBaseUrl);

  page.on('pageerror', error => measurements.browserErrors.push(error.message));
  page.on('console', message => {
    if (message.type() === 'error') measurements.browserErrors.push(message.text());
  });
  page.on('requestfailed', request => {
    if (request.url().startsWith(apiOrigin)
      && request.failure()?.errorText !== 'net::ERR_ABORTED') {
      measurements.browserErrors.push(
        `${request.method()} ${request.url()}: ${request.failure()?.errorText || 'request failed'}`,
      );
    }
  });
  page.on('response', response => {
    if (response.url().startsWith(apiOrigin) && response.status() >= 400) {
      measurements.browserErrors.push(`API ${response.status()}: ${response.url()}`);
    }
    if (!/\/test-scenarios\//.test(response.url()) && !/\/replan(?:\?|$)/.test(response.url())) return;

    responseReadTasks.push((async () => {
      try {
        const body = await response.body();
        const headers = await response.allHeaders();
        const timing = response.request().timing();
        const responseMs = timing.responseEnd >= 0 && timing.requestStart >= 0
          ? Math.round(timing.responseEnd - timing.requestStart)
          : null;
        measurements.apiResponses.push({
          url: response.url(),
          status: response.status(),
          responseMs,
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
  await page.waitForFunction(
    () => window.__AIRSPACE_EVENTS__?.some(message => message.event === 'scenarioLoaded'),
    null,
    { timeout: 90000 },
  );
  measurements.scenarioDataMs = Math.round(performance.now() - coldStart);
  await page.waitForFunction(
    () => window.__AIRSPACE_EVENTS__?.some(
      message => message.event === 'status' && message.message === 'Scene ready.',
    ),
    null,
    { timeout: 90000 },
  );
  measurements.coldLoadMs = Math.round(performance.now() - coldStart);
  measurements.renderer = await page.evaluate(
    () => window.__AIRSPACE_PERFORMANCE__?.() || null,
  );
  measurements.javascriptResources = await page.evaluate(() => (
    performance.getEntriesByType('resource')
      .filter(resource => /\.js(?:\?|$)/.test(resource.name))
      .map(resource => ({
        url: resource.name,
        transferBytes: resource.transferSize || null,
        encodedBytes: resource.encodedBodySize || null,
      }))
  ));
  measurements.modelResources = await page.evaluate(() => (
    performance.getEntriesByType('resource')
      .filter(resource => /\.(?:glb|gltf)(?:\?|$)/i.test(resource.name))
      .map(resource => ({
        url: resource.name,
        durationMs: Math.round(resource.duration),
        transferBytes: resource.transferSize || null,
        encodedBytes: resource.encodedBodySize || null,
      }))
  ));

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

  const readyMessage = await page.evaluate(() => (
    window.__AIRSPACE_EVENTS__?.find(message => message.event === 'ready') || null
  ));
  const availableScenarios = new Set((readyMessage?.scenarios || []).map(scenario => scenario.id));
  const unavailable = requestedScenarios.filter(scenario => !availableScenarios.has(scenario));
  if (unavailable.length > 0) {
    throw new Error(`Unknown benchmark scenario(s): ${unavailable.join(', ')}`);
  }

  for (const scenario of requestedScenarios) {
    const startIndex = await page.evaluate(() => window.__AIRSPACE_EVENTS__.length);
    const started = performance.now();
    await page.evaluate(selected => window.AirspaceThree.receiveMessage({
      version: 1,
      type: 'command',
      action: 'loadScenario',
      scenario: selected,
    }), scenario);
    await page.waitForFunction(
      ({ selected, startIndex: index }) => window.__AIRSPACE_EVENTS__
        .slice(index)
        .some(message => message.event === 'scenarioLoaded' && message.scenario === selected),
      { selected: scenario, startIndex },
      { timeout: switchTimeoutMs },
    );
    measurements.scenarioSwitchMs.push(Math.round(performance.now() - started));
  }

  await Promise.all(responseReadTasks);
  measurements.finishedAt = new Date().toISOString();
  measurements.bridgeEvents = await page.evaluate(() => (
    window.__AIRSPACE_EVENTS__
      .filter(message => ['error', 'status', 'scenarioLoaded'].includes(message.event))
      .slice(-20)
  ));
  console.log(JSON.stringify(measurements, null, 2));
  if (measurements.browserErrors.length > 0) process.exitCode = 1;
} catch (error) {
  measurements.benchmarkError = error.message;
  if (page && !page.isClosed()) {
    measurements.bridgeEvents = await page.evaluate(() => (
      window.__AIRSPACE_EVENTS__
        .filter(message => ['error', 'status', 'scenarioLoaded'].includes(message.event))
        .slice(-20)
    )).catch(() => []);
  }
  console.error(JSON.stringify(measurements, null, 2));
  process.exitCode = 1;
} finally {
  await browser.close();
}
