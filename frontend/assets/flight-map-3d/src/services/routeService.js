const API_BASE_URL =
    (typeof window !== 'undefined' && window.AIRSPACE_API_BASE)
    || new URLSearchParams(window.location.search).get('api')
    || 'http://localhost:8000';
// 20s: the first synthetic multi-flight request can legitimately take a few
// seconds while A* runs; 8s aborted it and surfaced as "stuck on loading".
const REQUEST_TIMEOUT_MS = 20000;

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
        await fetchJson(`${API_BASE_URL}/health`);
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
    return fetchJson(`${API_BASE_URL}/test-scenarios/${encodeURIComponent(scenario)}?${query}`, { signal });
}

export async function replanWeatherScene(previousPayload, routeProgress, weatherSeed, signal) {
    return fetchJson(`${API_BASE_URL}/replan`, {
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