const API_BASE_URL =
    (typeof window !== 'undefined' && window.AIRSPACE_API_BASE) || 'http://localhost:8000';
const REQUEST_TIMEOUT_MS = 8000;

async function fetchJson(url, options = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    try {
        const response = await fetch(url, { ...options, signal: controller.signal });
        if (!response.ok) {
            const body = await response.json().catch(() => null);
            throw new Error((body && body.detail) || `Request failed (${response.status})`);
        }
        return response.json();
    } catch (error) {
        if (error.name === 'AbortError') {
            throw new Error(`Request timed out after ${REQUEST_TIMEOUT_MS / 1000}s`);
        }
        throw error;
    } finally {
        clearTimeout(timer);
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

export async function fetchSceneData(scenario, routeProgress = 0.35) {
    const query = new URLSearchParams();
    if (scenario === 'in-flight-replan') {
        query.set('route_progress', String(routeProgress));
    }
    return fetchJson(`${API_BASE_URL}/test-scenarios/${encodeURIComponent(scenario)}?${query}`);
}

export async function replanWeatherScene(previousPayload, routeProgress, weatherSeed) {
    return fetchJson(`${API_BASE_URL}/replan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
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