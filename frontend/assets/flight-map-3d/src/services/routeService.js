function defaultApiBaseUrl() {
    if (typeof window !== 'undefined' && window.AIRSPACE_API_BASE) {
        return window.AIRSPACE_API_BASE;
    }
    if (typeof navigator !== 'undefined' && /Android/i.test(navigator.userAgent)) {
        return 'http://10.0.2.2:8000';
    }
    return 'http://localhost:8000';
}

let apiBaseUrl = defaultApiBaseUrl();
const REQUEST_TIMEOUT_MS = 8000;

export function setApiBaseUrl(value) {
    let parsed;
    try {
        parsed = new URL(value);
    } catch {
        throw new Error('Backend URL must be an absolute HTTP(S) URL.');
    }
    if (!['http:', 'https:'].includes(parsed.protocol) || parsed.username || parsed.password
        || parsed.search || parsed.hash) {
        throw new Error('Backend URL must be HTTP(S), without credentials, query, or fragment.');
    }
    apiBaseUrl = parsed.href.replace(/\/+$/, '');
}

async function fetchJson(url, options = {}) {
    const { signal: externalSignal, ...requestOptions } = options;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    const abortFromCaller = () => controller.abort();
    if (externalSignal) {
        if (externalSignal.aborted) abortFromCaller();
        else externalSignal.addEventListener('abort', abortFromCaller, { once: true });
    }

    try {
        const response = await fetch(url, { ...requestOptions, signal: controller.signal });
        if (!response.ok) {
            const body = await response.json().catch(() => null);
            throw new Error((body && body.detail) || `Request failed (${response.status})`);
        }
        return response.json();
    } catch (error) {
        if (externalSignal && externalSignal.aborted) throw error;
        if (error.name === 'AbortError') {
            throw new Error(`Request timed out after ${REQUEST_TIMEOUT_MS / 1000}s`);
        }
        throw error;
    } finally {
        clearTimeout(timer);
        if (externalSignal) externalSignal.removeEventListener('abort', abortFromCaller);
    }
}

export async function checkBackendHealth() {
    try {
        await fetchJson(`${apiBaseUrl}/health`);
        return { ok: true };
    } catch (error) {
        return { ok: false, detail: error.message };
    }
}

export async function fetchSceneData(scenario, routeProgress = 0.35, signal) {
    const query = new URLSearchParams();
    if (scenario === 'in-flight-replan') {
        query.set('route_progress', String(routeProgress));
    }
    return fetchJson(`${apiBaseUrl}/test-scenarios/${encodeURIComponent(scenario)}?${query}`, { signal });
}

export async function replanWeatherScene(previousPayload, routeProgress, weatherSeed, signal) {
    return fetchJson(`${apiBaseUrl}/replan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal,
        body: JSON.stringify({
            previous_grid: previousPayload.grid,
            previous_route: previousPayload.routes.optimized,
            previous_source: previousPayload.meta.source,
            grid_config: previousPayload.meta.grid_config,
            route_progress: routeProgress,
            mode: previousPayload.routes.reasoning.mode,
            weather_seed: weatherSeed,
        }),
    });
}