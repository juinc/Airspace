# Airspace repository discovery

Discovery date: 2026-11-01

## Project shape

Airspace is a weather-aware route visualization. The FastAPI backend owns
weather acquisition and normalization, grid coordinates, aircraft assumptions,
A* route planning, route metrics, and replanning. Flutter owns the application
interface. The bundled Three.js scene renders backend payloads and reports
route-coordinate picks; it does not plan routes.

## Runtime and dependency map

| Area | Entry points | Responsibility |
|---|---|---|
| FastAPI | `backend/main.py` | API/CORS, live scene assembly, scenario LRU cache |
| Weather | `backend/weather/{client,normalize,events,cache}.py` | Open-Meteo AIFS, cache, exposure scores, event detection |
| Grid and coordinates | `backend/grid/{builder,romania_mask,coordinates}.py` | 0.5° sampling, Romania mask, shared scene coordinates |
| Optimizer | `backend/optimizer/{astar,stub_trajectory}.py` | 3D A*, modeled flight phases, metrics and replanning |
| Synthetic scenes | `backend/synthetic_scenarios.py` | Seeded weather fields, synthetic routes and multi-flight scenarios |
| Flutter UI | `frontend/lib/utils/overlay_3js.dart`, `overlay_elements/*` | Scenario, camera/layer, status, metrics, telemetry, coordinate UI |
| Flutter protocol | `frontend/lib/airspace_protocol.dart`, `three_view*.dart` | Versioned v1 message parsing, commands, platform transports |
| Three.js | `frontend/assets/flight-map-3d/src/main.js`, `sceneData.js`, `core/*`, `objects/*`, `utils/*` | Canvas renderer, backend scene geometry, picking and telemetry |
| Packaged scene | `frontend/assets/flight-map-3d/dist/build/` | Vite output bundled by Flutter |

Flutter loads the packaged scene rather than a Vite development server.
Android/iOS use `webview_flutter`; Windows uses `webview_windows` and a
loopback server for Flutter assets; Flutter web uses an iframe. See
[BRIDGE_PROTOCOL.md](./frontend/assets/flight-map-3d/BRIDGE_PROTOCOL.md) for
message fields and startup order.

## API and data flow

The scene payload includes `meta`, `grid`, `events`, `airports`, and `routes`;
multi-flight payloads also include `flights`. Scene coordinates and all route
geometry come from the backend. The Three.js route inspector maps a picked
scene position back to a coordinate and selects the nearest backend weather
sample. Flutter displays the resulting v1 event and does not fabricate
telemetry or weather.

The scenario list is sent by the scene in `ready.scenarios`. Registered
synthetic scenarios include `crossroads-storm`, `converge-bucharest`,
`carpathian-siege`, `random-storms`, `heavy-storms`, `layered-random`,
`clear-airspace`, `storm-wall`, `over-the-top`, `low-corridor`, `slalom`,
`fuel-critical`, and `in-flight-replan`. `drastic-weather-change` is a backend
compatibility alias. `real-meteo` calls Open-Meteo and reports provider errors;
it has no synthetic fallback.

Live and synthetic full-country grids use a 0.5° envelope over Romania,
typically about 136 horizontal cells and five pressure levels. Synthetic
weather responses are cached in a bounded 16-entry LRU with deep-copied
responses; different cache misses can build concurrently. The default
multi-flight scenario is prewarmed from FastAPI lifespan startup. Concurrent
requests for the same uncached scenario share one build; different scenario
keys can still build concurrently.

## Verified behavior and known constraints

- Flutter owns the controls and panels; the Three.js page is a fullscreen
  canvas with picking, telemetry and layer visibility commands.
- `clear-airspace` and the requested random/heavy/layered scenarios are
  registered. `drastic-weather-change` aliases the existing in-flight replan.
- Per-event dot rendering was removed; weather is represented by the
  instanced mesh spans. Airport markers, routes, altitude references and route
  picking remain separate scene layers.
- Backend CORS covers local development origins, Android WebView asset origins
  and the opaque `null` origin used by some packaged WebViews. Android cleartext
  HTTP is enabled for local development; production should use HTTPS.
- Backend URL is configurable in Flutter. `10.0.2.2` is only the Android
  emulator host; physical devices require a reachable host/LAN address.
- `real-meteo` depends on the external provider and can fail with provider
  errors/rate limits. It is not replaced with generated data.
- Aircraft performance values are modeled assumptions, not POH/dispatch or
  live aircraft data. This prototype is not for flight planning.
- No time/altitude slider exists; none is shown.

## Verification

The Vite production build passes, with one chunk above Vite's 500 KB warning
threshold. The backend suite passes (89 tests). The frontend benchmark uses
Playwright Chromium mobile emulation against the packaged build and a local
FastAPI instance; it records scene-ready time, scenario switches, API payload
sizes, console errors, and FPS. The latest run measured 15.5 s to full scene
ready, 1.36 s to scenario data, 1.6–5.4 s for scenario switches, and 7 FPS;
there were no browser errors. Its headless FPS is a software-renderer result,
not a physical-device measurement, and the production renderer stats hook
returned null. On the dev build, renderer info was 64 draw calls, 563,120
triangles, 39 geometries, 12 textures and DPR 1.

The mobile terrain model is 3.38 MB and the mobile aircraft model is 0.21 MB;
the desktop terrain model is 28.57 MB. These are source asset sizes, not
resident GPU memory.

Node and the Vite dependencies are available. Python 3.12 and the backend
virtual environment are available. Flutter/Dart is not on PATH, so Flutter
formatting, analysis, widget tests, native builds and device rendering could
not be run here.
