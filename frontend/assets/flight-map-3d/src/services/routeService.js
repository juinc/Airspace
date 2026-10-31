const API_BASE_URL = 'http://localhost:8000';

export async function fetchSceneData(scenario) {
  const response = await fetch(
    `${API_BASE_URL}/test-scenarios/${encodeURIComponent(scenario)}`,
  );
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail || `Scenario request failed (${response.status})`);
  }

  return response.json();
}