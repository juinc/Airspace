below).
# Airspace

Airspace is a research/demo application for **visualizing weather-aware flight
route optimization**. A Python backend retrieves an ECMWF AIFS forecast from
Open-Meteo, builds a Romania-shaped weather grid, scores weather exposure, and
searches for routes with A*. A Flutter application hosts an interactive Three.js
scene that compares a direct baseline with one or more optimized routes.

This is a visualization prototype, not an aviation weather product, dispatch
system, flight-planning tool, collision-avoidance system, or source of
operational advice. The forecast resolution, simplified border mask, weather
classification, aircraft performance assumptions, and route constraints are
not certified or validated for flight operations.

## What the application does

The selectable scene is driven by the backend. It can show synthetic, seeded
weather demonstrations without a weather-provider request, or request the
current AIFS forecast. The backend returns weather cells, detected events,
airports, a baseline route, an optimized route, route metrics, and assumptions
as JSON. The Three.js client turns that payload into a 3D scene with terrain,
weather, route lines, aircraft, route inspection, and camera controls. Flutter
provides the application shell and overlays scene status, route metrics, the
pressure-level legend, aircraft state, and selection controls.

The optimizer is classical A* search; it is not machine learning. ECMWF AIFS is
the forecast source. Route costs trade modeled time against weather exposure,
with three user-selectable preference modes. Synthetic scenarios are useful for
repeatable demos, but they are handcrafted weather fields, not observed or
forecast meteorology.

## Architecture

```text
                         HTTPS/JSON
  Open-Meteo AIFS  <---------------------  FastAPI backend
                                                |
                                                | scene JSON / route commands
                                                v
                                         Three.js + Vite
                                         GLB assets, terrain,
                                         weather, routes, planes
                                                ^
                                                | WebView / iframe bridge
                                                |
                                       Flutter application
                                 controls, metrics, status, HUD
```

In development the scene is served by Vite on port 5173, the API by Uvicorn on
port 8000, and Flutter loads the Vite URL. Flutter Web embeds the scene in an
iframe; Android/iOS/macOS use `webview_flutter`; Windows uses WebView2 through
`webview_flutter_windows`. The scene and Flutter UI exchange JSON events and
commands over platform-specific bridge transports.

**Important deployment status:** `npm run build` creates a Vite production
bundle under `frontend/assets/flight-map-3d/dist/build`, but the current Flutter
host still loads a URL from `resolveSceneUrl()` and the bundle is not wired into
Flutter's asset manifest. A release app therefore still needs a reachable scene
server and API unless a future change adds platform-specific bundled-asset
loading. The PowerShell and Bash launchers are development launchers; they are
not production service managers.

## Repository map

```text
backend/
  main.py                 FastAPI app, requests, response assembly, caches
  grid/                   Grid generation, Romania mask, scene coordinates
  optimizer/              A*, aircraft profile, route phases and metrics
  weather/                Open-Meteo client, normalization, events, cache
  synthetic_scenarios.py  Seeded demo weather and multi-flight plans
  tests/                  Backend unit and API tests
frontend/
  lib/                    Flutter app, data models, bridge and WebView hosts
  test/                   Flutter unit tests
  android/, ios/, windows/ Native Flutter runner projects
  assets/flight-map-3d/
    src/                  Three.js renderer, scene objects, bridge, services
    public/models/        Romania terrain and aircraft GLB assets
    package.json          Vite/Three.js scripts and dependencies
run_airspace.ps1          Windows PowerShell development launcher
run_airspace.sh           Bash development launcher
```

## Requirements

Use the versions below as the supported baseline. The repository pins backend
Python packages and Flutter/Dart dependencies in their respective manifests.

| Tool/platform | Requirement |
| --- | --- |
| Python | Python 3.11 or 3.12 recommended; Python 3.12 is the tested local setup |
| Node.js/npm | Node.js 20.19+ or 22.12+; npm comes with Node.js. This is required by the locked Vite 8 toolchain |
| Flutter/Dart | Flutter 3.44+ stable (Dart 3.12+); `pubspec.yaml` requires Dart `^3.12.0` |
| Windows | Windows 10 version 1809 or newer, Visual Studio 2022 Desktop C++ workload, and Microsoft Edge WebView2 Runtime |
| Android | Android SDK, platform tools, an emulator or device, and NDK `28.2.13676358` (the Flutter SDK's current `ndkVersion`) |
| iOS | macOS, Xcode, CocoaPods, and an iOS simulator/device |
| Linux | Linux desktop build support is included for local development; install the backend venv, Node/NPM, and the GTK WebKit runtime (`sudo apt-get install libwebkit2gtk-4.1-dev libjavascriptcoregtk-4.1-dev` on Debian/Ubuntu), then launch with `bash ./run_airspace.sh --device linux` |

Backend runtime dependencies are in `backend/requirements.txt`; test-only
dependencies are added in `backend/requirements-dev.txt`. Flutter dependencies
are in `frontend/pubspec.yaml` and `frontend/pubspec.lock`. JavaScript
dependencies are locked in `frontend/assets/flight-map-3d/package-lock.json`.

## Quick start

### Install dependencies

From the repository root in Bash (Linux/macOS/Git Bash):

```bash
python3.12 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements-dev.txt
npm ci --prefix frontend/assets/flight-map-3d
cd frontend
flutter pub get
cd ..
```

From PowerShell on Windows:

```powershell
py -3.12 -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
npm ci --prefix frontend\assets\flight-map-3d
Push-Location frontend
flutter pub get
Pop-Location
```

### Start everything for development

The repository launchers start or reuse the API and Vite servers, wait for
their readiness checks, then run Flutter in the foreground. Press Ctrl+C (or
`q` in the Flutter runner) to exit. Only service processes started by the
launcher are stopped; services that were already listening are reused.

PowerShell:

```powershell
.\run_airspace.ps1 -Device windows
.\run_airspace.ps1 -Device chrome
.\run_airspace.ps1 -Device emulator-5554
```

Bash:

```bash
bash ./run_airspace.sh --device linux
bash ./run_airspace.sh --device windows
bash ./run_airspace.sh --device chrome
bash ./run_airspace.sh --device emulator-5554
```

Replace the example device ID with one reported by `flutter devices`. The
launchers default to the host OS (`linux` on Linux, `macos` on macOS, and
`windows` on Windows); Bash accepts `--device` and `--host`, and PowerShell
accepts `-Device` and `-DevHost`.

Android emulator networking uses `10.0.2.2` to reach the development machine.
For a physical phone on the same network, provide the computer's LAN IP and
ensure the firewall permits inbound traffic on ports 5173 and 8000:

```powershell
.\run_airspace.ps1 -Device <device-id> -DevHost 192.168.1.25
```

```bash
bash ./run_airspace.sh --device <device-id> --host 192.168.1.25
```

The backend's `AIRSPACE_CORS_ORIGINS` is set by the launcher when it starts the
backend. If the launcher reuses an already-running backend, that process keeps
its original CORS configuration. Restart it with the appropriate
`AIRSPACE_CORS_ORIGINS` value when changing to a physical-device host. iOS
simulators and physical iPhones also need a host address that routes back to the
development machine; pass it with `--host`/`-DevHost` when necessary.

### Run the components separately

Backend (from the repository root):

```bash
backend/.venv/bin/python -m uvicorn main:app --app-dir backend --host 0.0.0.0 --port 8000 --reload
```

PowerShell equivalent:

```powershell
backend\.venv\Scripts\python.exe -m uvicorn main:app --app-dir backend --host 0.0.0.0 --port 8000 --reload
```

Three.js development server:

```bash
npm --prefix frontend/assets/flight-map-3d run dev -- --host 0.0.0.0 --strictPort
```

Flutter, in another terminal:

```bash
cd frontend
flutter devices
flutter run -d linux
flutter run -d windows
```

The Flutter app defaults to `http://localhost:5173/?api=http://localhost:8000`.
Android emulator defaults to `10.0.2.2`; compile-time overrides are available:

```bash
flutter run -d emulator-5554 --dart-define=AIRSPACE_DEV_HOST=10.0.2.2
```

`AIRSPACE_SCENE_PORT` and `AIRSPACE_API_PORT` can override the default ports
when running Flutter manually. The combined launchers currently assume Vite
5173 and API 8000.

## Python backend

### Components

| Module | Responsibility |
| --- | --- |
| `backend/main.py` | FastAPI routes and models, CORS/gzip, forecast fetch orchestration, scene payloads, bounded scenario cache, replan responses |
| `backend/weather/client.py` | Open-Meteo POST requests, AIFS-valid-time selection, normalization of provider responses |
| `backend/weather/normalize.py` | Null-aware 0-100 exposure score |
| `backend/weather/events.py` | Weather classification and 8-connected component clustering |
| `backend/weather/cache.py` | Atomic JSON file cache with six-hour TTL |
| `backend/grid/builder.py` | Regular latitude/longitude point generation |
| `backend/grid/romania_mask.py` | Simplified ray-cast polygon plus border-vertex buffer |
| `backend/grid/coordinates.py` | Single authoritative geographic-to-scene transform and altitude conversion |
| `backend/optimizer/astar.py` | Aircraft profile, graph construction, A*, route geometry, collision-clearance checks, replanning assessment, metrics |
| `backend/optimizer/stub_trajectory.py` | Direct baseline and route resampling |
| `backend/synthetic_scenarios.py` | Seeded synthetic weather, events, flight pairs, and seeded route blockages |

All API handlers are synchronous `def` handlers. FastAPI runs them in its
worker thread pool so CPU-bound graph construction and A* do not block the
async event loop. Startup pre-warms three synthetic scenarios on a daemon
thread as a best-effort latency optimization.

### Forecast and grid

The live provider is Open-Meteo's `ecmwf_aifs025_single` model. The client
requests two forecast days and asks for surface precipitation, cloud cover,
CAPE and, at each pressure level, temperature, relative humidity, wind speed,
wind direction, vertical velocity, and geopotential height. Requests use a
JSON POST body in chunks of at most 250 coordinates. The client selects the
first timestamp that is both in the future and on the six-hour AIFS cadence.
Returned forecast timestamps are retained in payload metadata; the UI should
not imply hourly forecast precision.

The default live and synthetic grid envelope is 43.5-48.5 degrees north and
19.5-30.0 degrees east, sampled every 0.5 degrees and filtered by a simplified
Romania outline with a 0.15-degree vertex buffer. This currently yields 136
horizontal points. Test mode truncates `/weather-grid` and scene-data requests
to the first 36 points. Full `/weather-events` test mode instead checks only
the two route airports. The five pressure levels are 500, 400, 300, 250, and
200 hPa; full live weather therefore has up to 680 grid-layer nodes.

The border is a hand-specified approximate polygon, not an authoritative
administrative boundary. The grid's rectangular envelope contains areas beyond
Romania, but the mask removes most outside points. A weather forecast cell is a
coarse model sample, not a radar pixel or a guarantee of conditions at a
particular altitude.

### Exposure score

Each pressure-level node receives a weather exposure score from 0 to 100. Raw
inputs are clamped and normalized into `[0, 1]` using these ranges:

| Input | Normalization range | Weight |
| --- | ---: | ---: |
| CAPE | 0-3000 J/kg | 0.35 |
| Precipitation | 0-20 mm | 0.25 |
| Absolute vertical velocity | 0-3 (provider units) | 0.20 |
| Relative humidity | 0-100% | 0.10 |
| Cloud cover | 0-100% | 0.10 |

For the available components, the implementation computes the weighted mean
and scales it to 100. Missing, invalid, NaN, or infinite values are omitted and
the remaining weights are renormalized; missing data is not silently treated
as zero exposure. If all components are missing, the score is `null`.

These are optimizer inputs and visualization values, not certified aviation
hazard thresholds. The synthetic weather generator and event classifier use
separate threshold rules described below.

### Weather event detection

For each pressure level, the event classifier considers CAPE, precipitation,
vertical velocity, and wind speed. A convective point requires CAPE at least
1000 and absolute vertical velocity at least 1.5. It is labeled
`severe_storm` when that convective condition also has CAPE at least 2500 or
wind speed at least 100 km/h; otherwise it is `thunderstorm`. Non-convective
precipitation of at least 1 mm is `rain`. Incomplete fields can yield
`unknown`; they are not reported as clear weather.

`scipy.ndimage.label` groups matching cells using a 3x3 neighborhood, so
diagonally touching cells belong to one event. Event output includes the type,
pressure level, 3D centroid, cell count, and geographic bounding box. Rain
events also get a light/heavy label, with 4 mm as the heavy threshold. This is
a coarse AIFS-derived proxy, not radar nowcasting or severe-weather detection.

### Grid and scene coordinates

`backend/grid/coordinates.py` owns the geographic transform. Scene origin is
45.625 degrees north, 24.875 degrees east. X is east/west kilometers; Z is
north/south kilometers; Y is altitude in scene units. Latitude uses 111.32 km
per degree. Longitude uses `111.32 * cos(origin latitude)` km per degree.
Altitude Y is multiplied by 4 for visual separation; route physics and metrics
use actual altitude in kilometers, not exaggerated Y.

Pressure-level altitude uses the provider geopotential height when available.
Fallback standard-atmosphere heights are used only when geopotential height is
unusable. Scene metadata also supplies Romania map bounds and a transformed
country border so the GLB model can be fitted to the same coordinate frame.

### A* heuristic and cost

The graph has one node for each usable weather grid point and pressure level.
Edges connect up to 26 neighbors: the surrounding 3x3 cells in the same layer
and in the layer directly above/below. Missing cells/layers remove nodes and
edges. Levels above the aircraft service ceiling are excluded. The default
profile is a nominal Cessna Citation CJ3 model.

For an edge, horizontal cruise time is horizontal kilometers divided by cruise
speed. Vertical time is altitude change divided by the modeled climb or descent
rate. The edge travel time is the larger of horizontal and vertical time,
representing climb/descent while moving forward. Weather and layer-change cost
are then added:

```text
edge_cost = travel_time * (1 + weather_weight * destination_exposure / 100)
            + altitude_change_penalty
```

The altitude-change penalty is applied when the pressure-level index changes.
If exposure is missing, its weather multiplier is 1 (no weather surcharge);
the route still carries missing exposure as `null` where appropriate.

The A* heuristic is straight horizontal distance to the goal divided by cruise
speed. It omits vertical and weather costs, which are non-negative, and is
therefore a lower bound for the implemented cost model. It is not a forecast of
actual flight time.

Mode weights are:

| Mode | Weather weight | Effect |
| --- | ---: | --- |
| `Fastest` | 0.5 | Prioritizes modeled travel time; weather has less influence |
| `Balanced` | 2.0 | Default compromise between time and exposure |
| `Lower-exposure` | 5.0 | Pays more modeled time to reduce exposure when possible |

Weather is a soft cost, not a hard no-fly exclusion. The planner can traverse
high-exposure nodes if their route cost is still lowest or the graph offers no
better path. The default start/goal layer is the lowest reachable altitude
layer, with nearest grid nodes selected for the airport coordinates.

### Flight phases, aircraft profile, and metrics

The optimized route's grid path is wrapped with ground roll, a continuous
climb, the A*-selected vertical profile, and a continuous descent/flare. The
climb uses a modeled 14 horizontal km per km gained and is capped at 40% of
route length; descent uses 16 horizontal km per km lost and is also capped at
40%, leaving at least 20% for cruise. Ground roll is 1.5 km. The transitions
ease over short segments, and the profile is sampled at approximately 8 km for
rendering. Replanning starts at the supplied airborne position and does not
add a second takeoff phase.

Default profile reference values include 416 kt maximum cruise speed, a
45,000 ft service ceiling, CJ3 maximum weights/range/fuel-capacity figures,
and a default gross-mass assumption at maximum takeoff weight. The 1189 m/min
climb rate, 600 m/min descent rate, 520 kg/h fuel burn, weight scaling, and
route fuel estimates are simulation assumptions; they are not POH/AFM or
dispatch values. A custom profile is accepted by `/optimize` and
`/test-scene-data`; query-based synthetic scenario routes use the default
profile.

Metrics are calculated over the full modeled route and include 3D physical
distance, time, waypoint-average exposure, altitude changes, climb/descent
time, estimated fuel burn, planned initial fuel with 25% reserve, remaining
fuel, and a fuel-capacity status when applicable. The direct baseline is a
straight airport-to-airport comparison at 250 hPa, wrapped in the same modeled
takeoff/landing geometry and resampled to match the optimized route's waypoint
count. It is a reference, not a second optimization result.

Multi-flight demos optimize flights sequentially and reserve each route against
later searches. En-route segments are checked in 3D against a 0.05 km minimum
centerline clearance. Takeoff and landing segments are excluded so routes may
share airport terminals. This is a visualization constraint, not separation
assurance or collision avoidance.

### Replanning

`POST /replan` compares the previous and updated weather exposure at samples
along the remaining route. A replan is considered drastic if one sampled
waypoint increases by at least 50 points, or at least two waypoints increase
by 25 points or more and the average increase is at least 25. When drastic,
A* restarts from the estimated in-flight position. Otherwise the existing route
is retained. These fixed thresholds are demo logic, not operational decision
criteria.

The `in-flight-replan` synthetic scenario starts from clear synthetic weather
and spawns a seeded severe-storm blockage ahead of the aircraft. Weather seeds
vary the blockage position/intensity while keeping a given seed repeatable.

### Caching and performance

Raw weather responses and complete live-scene payloads use a JSON cache at
`backend/runtime/cache/weather_cache.json` with a six-hour TTL. Writes use a
temporary file and atomic replacement. Cache keys include forecast model,
request variables, grid/configuration, pressure levels, forecast timestamp,
route, and aircraft/profile context as appropriate. Cache failures are
best-effort and do not crash the API.

Synthetic responses are also cached in process in a bounded 16-entry
insertion-order dictionary. The frontend uses low/mid/high device tiers with
weather-cell rendering caps of 120/300/500 respectively. These are rendering
budgets, not input data or forecast resolution.

## Synthetic scene scenarios

`GET /test-scenarios/{scenario}` serves seeded scenes without a weather-provider
request except for `real-meteo`.

| ID | Purpose |
| --- | --- |
| `crossroads-storm` | Three intersecting airport corridors with distinct storm walls |
| `converge-bucharest` | Four arrival routes converging on Bucharest around a storm ring |
| `carpathian-siege` | Three triangle routes around a central storm mass |
| `storm-wall` | Full-altitude wall with one lateral gap |
| `over-the-top` | Storms on lower layers; clear upper cruise layers |
| `low-corridor` | Storms on upper layers; clear lower layers |
| `slalom` | Alternating storm columns encourage lateral changes |
| `fuel-critical` | Far-edge gap creates a long-detour fuel demonstration |
| `in-flight-replan` | Clear route followed by a seeded blockage ahead |
| `real-meteo` | Full live AIFS scene, subject to provider/network availability |

The internal generator also has a `clear-airspace` base field used by the
replanner, but `clear-airspace` is intentionally not exposed as a selectable
scenario endpoint. Unknown scenario IDs return 404.

## HTTP API

Interactive OpenAPI documentation is available at `http://127.0.0.1:8000/docs`
when the backend is running. Except for `/health`, `/test-weather`, and the
scenario GET route, the endpoints below accept JSON POST bodies.

| Route | Request / response |
| --- | --- |
| `GET /health` | Liveness check: `{"status":"ok"}` |
| `GET /test-weather` | Fetches forecast data for Craiova and Cluj; returns data, source, model and forecast-time metadata |
| `POST /weather-grid` | Grid settings and `test_mode`; returns `point_count`, grid config, scene config, metadata, and `data` cells |
| `POST /weather-events` | Grid settings and `test_mode`; returns `events` plus `checked_points` |
| `POST /test-scene-data` | Grid settings, route mode, aircraft profile, `test_mode`; returns full live scene (`meta`, `grid`, `events`, `airports`, `routes`) |
| `POST /optimize` | Mode and aircraft profile; fetches live weather and returns baseline/optimized routes and metrics |
| `POST /replan` | Prior grid/route, progress, source, mode and optional seed/config; returns weather update assessment and route |
| `GET /test-scenarios/{scenario}` | `mode`, `route_progress`, `weather_seed` query parameters; returns a synthetic or live scene payload |

Grid requests can override `min_lat`, `max_lat`, `min_lon`, `max_lon`,
`lat_step`, and `lon_step`. Omitted values use the defaults documented above.
`test_mode` defaults to true for `GridRequest` endpoints and truncates regular
scene grids to 36 cells; `/optimize` defaults it to false. Invalid bounds or
route modes return 400, an unknown scenario returns 404, and weather-provider
request/timestamp failures return 502.

### Scene payload shape

Full scene endpoints return the following top-level structure. Multi-flight
scenarios also return `flights`; `routes` is retained as a compatibility alias
to the first flight.

```json
{
  "meta": {
    "source": "synthetic | live | cache",
    "scenario": "storm-wall",
    "weather_model": "ecmwf_aifs025_single",
    "forecast_step_hours": 6,
    "forecast_valid_time": "...",
    "origin_lat": 45.625,
    "origin_lon": 24.875,
    "scene_unit": "km",
    "vertical_exaggeration": 4,
    "map_bounds": {"min_x": 0, "max_x": 1, "min_z": 0, "max_z": 1},
    "routing_assumptions": {},
    "trajectory_status": "..."
  },
  "grid": [
    {
      "lat": 45.5,
      "lon": 24.5,
      "forecast_time": "...",
      "x": 0,
      "z": 0,
      "cape": 0,
      "precipitation": 0,
      "cloud_cover": 0,
      "levels": {
        "250": {
          "temperature": null,
          "wind_speed": null,
          "wind_direction": null,
          "vertical_velocity": null,
          "relative_humidity": null,
          "geopotential_height": null,
          "exposure_score": null,
          "altitude_km": null,
          "y": null
        }
      }
    }
  ],
  "events": [],
  "airports": [],
  "routes": {
    "baseline": [],
    "optimized": [],
    "metrics": {"baseline": {}, "optimized": {}},
    "reasoning": {"mode": "balanced"}
  }
}
```

Scene coordinates and route geometry are backend-produced. Numeric weather
fields may be null when the provider omits data; consumers should preserve
unknown values rather than converting them to zero-risk values.

## Flutter and Three.js integration

`frontend/lib/main.dart` builds the Vite URL and injects the API URL as an
`api` query parameter. `AIRSPACE_DEV_HOST` overrides the hostname;
`AIRSPACE_SCENE_PORT` and `AIRSPACE_API_PORT` override the ports.

| Host | Implementation | Bridge transport |
| --- | --- | --- |
| Flutter Web (Chrome/Edge) | iframe registered as a platform view | `window.postMessage` with JSON strings |
| Android/iOS/macOS | `webview_flutter` | JavaScript channel (`airspaceChannel`) |
| Windows | `webview_flutter_windows` using Microsoft Edge WebView2 | `window.chrome.webview.postMessage` |

The JS bridge sends typed `airspace:*` events to the host and accepts typed
commands such as scenario selection, camera preset, layer visibility, weather
replan, flight selection, and route selection. Flutter exposes host-independent
event models in `frontend/lib/services/airspace_bridge_service.dart`.

The Three.js scene loads `romania.glb` on desktop and
`romania-mobile.glb` on mobile, plus aircraft GLBs under
`frontend/assets/flight-map-3d/public/models`. It fits the map to backend scene
bounds, builds a terrain height sampler for route/airport alignment, and
renders baseline/optimized paths, aircraft, pressure-level grid, airports, and
weather clusters. Camera controls and route inspection live in the scene;
Flutter overlays the app controls and metrics. The scene and Flutter each
maintain scenario titles, so keep their registries synchronized when adding a
scenario.

## Platform support

| Platform | Status and requirements |
| --- | --- |
| Windows | Supported by the current development host. Requires Windows 10 1809+, WebView2 Runtime, and the Visual Studio C++ desktop workload. |
| Android | Supported through Android WebView. Emulator host is `10.0.2.2`; physical devices need the computer's LAN IP and an allowed firewall route. Debug manifest permits local HTTP for development. |
| iOS | Uses WKWebView. Build/run requires macOS and Xcode. For a physical iPhone, point `--host`/`-DevHost` at the computer's LAN IP. |
| macOS | Uses the WKWebView implementation. The current launcher can be given a macOS Flutter device ID. |
| Flutter Web | Supported in Chrome/Edge using the iframe host. The Vite page and API must be reachable from the browser. |
| Linux desktop | Supported for the current Linux desktop build. Verified locally with `flutter build linux --debug`; install the backend venv, Node.js/NPM, and the WebKit GTK libraries before launching the Bash wrapper. |

For Windows WebView2 runtime troubleshooting, confirm the Evergreen WebView2
Runtime is installed. On Android, the debug application uses cleartext HTTP
for the local Vite server; do not use that development setup as a production
network-security policy. iOS local HTTP is enabled only for local networking.

## Build and deployment status

The Linux WebView runtime requires the system libraries for WebKit GTK. On Debian/Ubuntu:

```bash
sudo apt-get install libwebkit2gtk-4.1-dev libjavascriptcoregtk-4.1-dev
```

The Vite build command is:

```bash
npm --prefix frontend/assets/flight-map-3d run build
```

It outputs `frontend/assets/flight-map-3d/dist/build`. The build uses relative
asset URLs so it can be hosted below a path. However, the current Flutter IO
host calls `loadRequest()` with the Vite development URL, and Flutter Web uses
an iframe URL; `pubspec.yaml` does not include the Vite output. Therefore this
build alone does not make an offline/self-contained mobile or Windows release.
Before distribution, choose and implement a production scene-host strategy
(bundle/serve local assets or host them over HTTPS), configure the production
API URL, use HTTPS for the backend, and test the packaged app on each target.

The backend currently has no authentication, user accounts, database, or
production deployment configuration. Do not expose its development Uvicorn
server to untrusted networks.

## Testing and verification

Backend tests (network calls are mocked; cache tests use temporary paths):

```bash
cd backend
python -m pytest -q
```

Install dev requirements first with `python -m pip install -r
requirements-dev.txt`. Flutter tests:

```bash
cd frontend
flutter test
```

Flutter static analysis and platform build examples:

```bash
cd frontend
flutter analyze
flutter build linux --debug
flutter build windows --debug
flutter build web --debug
flutter build apk --debug
```

Three.js production compilation:

```bash
npm --prefix frontend/assets/flight-map-3d run build
```

The Flutter test directory contains bridge payload tests. Backend coverage
includes coordinates, grid validation, normalization, event grouping, A* route
costs and constraints, cache behavior, API responses, synthetic scenarios, and
weather-client parsing. Live `/test-scenarios/real-meteo` is the only listed
scene that requires Open-Meteo; tests do not depend on the provider.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Launcher says backend venv missing | Create `backend/.venv` and install `backend/requirements-dev.txt`; Linux/macOS use `backend/.venv/bin/python`, Windows PowerShell uses `backend/.venv/Scripts/python.exe`. |
| Launcher says Three.js dependencies missing | Run `npm ci --prefix frontend/assets/flight-map-3d` (Linux/macOS use the `npm` installed on the host). |
| Flutter cannot find the device | Run `flutter devices`; pass the exact ID to `--device` or `-Device`. |
| Android build asks for NDK | Install NDK `28.2.13676358` through Android Studio SDK Manager or the Android SDK CLI. |
| Phone cannot load Vite/API | Use the host computer's LAN address, allow ports 5173/8000 through the firewall, and ensure the backend CORS origin matches `http://<host>:5173`. |
| Flutter says the scene did not respond | Check Vite at `http://127.0.0.1:5173` and confirm `AIRSPACE_DEV_HOST` is correct for the target device. |
| Scene loads but scenario fails | Check backend health at `http://127.0.0.1:8000/health`; synthetic scenarios should work without internet, `real-meteo` needs provider access. |
| Windows shows a WebView initialization error | Install/update the Microsoft Edge WebView2 Runtime. |
| Map model is unavailable | Check that `public/models/romania.glb` and `romania-mobile.glb` exist and inspect browser/WebView console output for model-loading errors. |

## Safety and interpretation

Route and fuel metrics are illustrative outputs from simplified assumptions.
Weather exposures and event labels are not operational hazard classifications.
Terrain clearance is not validated; weather is not a hard exclusion; route
separation is only a geometric demo constraint. This application must not be
used to plan, dispatch, or operate an aircraft.
