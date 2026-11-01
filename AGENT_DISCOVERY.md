# Airspace repository discovery

Discovery date: 2026-11-01

## Project shape

Airspace is a weather-aware flight-route visualization. The backend owns weather acquisition, grid normalization, geographic-to-scene coordinates, aircraft assumptions, and A* route planning. Flutter is intended to be the app shell. Three.js renders the map, routes, weather, airports, and aircraft inside a bundled Vite build.

## Runtime and dependency map

| Area | Entry points and dependencies | Responsibility |
|---|---|---|
| FastAPI | `backend/main.py`; FastAPI, Pydantic, Requests | HTTP routes, request models, CORS, response assembly, scenario cache |
| Weather | `backend/weather/client.py`, `normalize.py`, `events.py`, `cache.py`; Requests, NumPy, SciPy | Open-Meteo AIFS fetch/cache, null-aware exposure score, weather event detection |
| Grid and coordinates | `backend/grid/builder.py`, `romania_mask.py`, `coordinates.py` | Grid construction, Romania mask, one authoritative scene-coordinate transform |
| Route optimizer | `backend/optimizer/astar.py`, `stub_trajectory.py` | Aircraft profile, 3D A* costs, route phases, metrics and replanning |
| Synthetic fixtures | `backend/synthetic_scenarios.py` | Deterministic weather grids, demo scenarios, synthetic route plans |
| Flutter shell | `frontend/lib/main.dart`, `three_view*.dart`, `utils/overlay_3js.dart`, `utils/overlay_elements/*` | App frame and early route/status panels; this implementation is not yet connected to the scene payload |
| 3D app | `frontend/assets/flight-map-3d/src/main.js`, `sceneData.js`, `core/*`, `objects/*`, `utils/*` | Vite entry, Three.js renderer and controls, terrain/assets, routes, aircraft, weather meshes, route picking |
| Bundled scene | `frontend/assets/flight-map-3d/dist/build/` | Vite production output included by Flutter through `pubspec.yaml` |

No `AGENTS.md` file was found in the repository. The root `README.md` describes a 0.25°/288-point grid, while the live backend defaults to a wider 0.5° grid. The current backend tests also contain assumptions that no longer match the implementation.

## API and scene data contract

| Route | Method | Consumer / behavior |
|---|---|---|
| `/health` | GET | Liveness |
| `/weather-grid` | POST | Grid and forecast metadata |
| `/weather-events` | POST | Detected weather clusters |
| `/test-scene-data` | POST | Full live weather scene and A* routes |
| `/optimize` | POST | Route pair and metrics |
| `/replan` | POST | Weather-change assessment and updated route |
| `/test-scenarios/{scenario}` | GET | Synthetic or live scene payloads |

The scene payload is `meta`, `grid`, `events`, `airports`, and `routes`; optional multi-flight scenarios add `flights`. Coordinates and route geometry are backend-owned. The current Vite client loads `/test-scenarios/{scenario}` from `routeService.js`. The current Flutter app does not provide scenario selection or consume `onScenarioLoaded` data. The current scene page independently owns its scenario selector, status, route metrics, altitude legend, loading UI, and aircraft HUD. It also has an untyped one-way `postMessage` scenario shim, while the route inspector injects its own DOM panel.

## Baseline findings

- Flutter panels use a fixed-width `Row` and 290 px side panels; the narrow-screen layout is not responsive. The panel toggles animate, but the controls contain placeholder airport data (JFK/LHR, etc.) unrelated to the backend's Romanian routes.
- `ThreeView` loads a development server (`localhost:5173` or `10.0.2.2:5173`) instead of the bundled Vite scene. The web implementation also hard-codes the dev server.
- The Vite page still owns nearly all visible interface controls, contrary to the requested Flutter UI contract.
- The required `random-storms`, `heavy-storms`, and `layered-random` synthetic IDs are absent from the backend scenario registry and grid generator. `clear-airspace` is deliberately rejected by the scenario endpoint even though the generator and tests use it.
- `real-meteo` depends on an external provider; a truthful demo fallback is needed if the app contract must keep that scenario selectable while offline.
- The 3D route inspector has a raycaster plus an HTML panel. The status HUD is also created in Three.js and currently mixes scene-derived coordinates with backend route metrics.
- Weather uses grouped `InstancedMesh` clusters, with a 500-cell cap. The renderer currently enables antialiasing at all device tiers. OrbitControls already supports touch gestures, but panning is disabled.
- Scenario responses use a bounded insertion-order dictionary rather than an LRU. Synchronous FastAPI handlers run in FastAPI's worker thread pool; route search should remain backend-only.

## Verification constraints

Node and the Vite dependencies are available. A Python 3.12 backend virtual environment is present. The system Flutter SDK is not on PATH, so Dart analysis, Flutter builds, and native device rendering cannot be confirmed here. The first pytest attempt also exposed that the runner's default temporary directory is outside the writable workspace; rerun pytest with a workspace-local `--basetemp`.

