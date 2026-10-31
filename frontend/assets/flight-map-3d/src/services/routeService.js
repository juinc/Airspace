const API_BASE_URL = 'http://localhost:8000';

export async function fetchSceneData(scenario, routeProgress = 0.35) {
  const query = new URLSearchParams();
  if (scenario === 'drastic-weather-change') {
    query.set('route_progress', String(routeProgress));
  }
  const response = await fetch(
    `${API_BASE_URL}/test-scenarios/${encodeURIComponent(scenario)}?${query}`,
  );
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail || `Scenario request failed (${response.status})`);
  }

  return response.json();
}

export async function replanWeatherScene(previousPayload, routeProgress, weatherSeed) {
  const response = await fetch(`${API_BASE_URL}/replan`, {
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
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail || `Replan request failed (${response.status})`);
  }

  return response.json();
}