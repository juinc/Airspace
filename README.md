# Airspace

**A 3D weather-aware flight trajectory optimizer.**

Airspace computes and visualizes two flight paths between a fixed Romanian air
corridor — a naive direct route and a weather-optimized route — using real
ECMWF AIFS forecast data and a custom A\* search. Both routes are rendered in
an interactive 3D scene (Three.js) embedded inside a Flutter app, alongside
detected storm cells, airport markers, and route comparison metrics.

---

## How it works, in one paragraph

The backend fetches a real forecast grid from Open-Meteo's ECMWF AIFS model
over the Craiova→Cluj-Napoca corridor, scores each grid cell's weather
exposure (0–100) from CAPE, precipitation, vertical velocity, humidity, and
cloud cover, clusters adjacent high-exposure cells into labeled storm events,
converts every coordinate into local 3D scene space, and runs A\* to find a
path that balances travel time against weather exposure. The frontend
receives one JSON payload containing everything needed to render the scene —
no geographic or meteorological logic lives in the frontend at all.

---

## Architecture

```
┌──────────────────────┐        JSON over HTTP        ┌──────────────────────┐
│   Flutter App        │ ───────────────────────────▶ │  FastAPI Backend     │
│   (webview_flutter)  │ ◀─────────────────────────── │  (Python)            │
└──────────┬───────────┘                              └────────────┬─────────┘
           │ loads bundled                                         │ fetches
           │ Vite build                                            ▼
           ▼                                              ┌──────────────────┐
┌─────────────────────┐                                   │  Open-Meteo API  │
│  Three.js Scene     │                                   │  (ECMWF AIFS)    │
│  (grid, events,     │                                   └──────────────────┘
│   routes, airports) │
└─────────────────────┘
```

---

## Tech stack

| Layer                | Technology                                                                          |
| -------------------- | ----------------------------------------------------------------------------------- |
| Backend              | Python 3.11+, FastAPI, Uvicorn                                                      |
| Numerical processing | NumPy, SciPy (`ndimage.label` for storm clustering)                                 |
| Weather data         | ECMWF AIFS via [Open-Meteo](https://open-meteo.com) (`ecmwf_aifs025_single`)        |
| Route optimization   | Custom A* (not machine learning — AIFS is the ML component, A* is classical search) |
| Caching              | Local JSON file, 6-hour TTL (no database)                                           |
| Frontend shell       | Flutter (`webview_flutter`)                                                         |
| 3D scene             | Three.js, bundled via Vite, loaded as a local WebView asset                         |
| Testing              | pytest + httpx (`fastapi.testclient.TestClient`)                                    |

---

## Prerequisites

- Python 3.11+
- Node.js 18+ and npm
- Flutter SDK (stable channel)

---

## Running the project

### 1. Backend

```sh
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn main:app --reload
```

Backend runs at `http://127.0.0.1:8000`. Interactive API docs (Swagger UI)
are available at `http://127.0.0.1:8000/docs` — use this instead of `curl` on
Windows, where PowerShell's `curl` alias (`Invoke-WebRequest`) uses
incompatible flag syntax. If you need the terminal, use:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -Method GET
```

### 2. Three.js scene (standalone development)

For iterating on the 3D scene without rebuilding the Flutter app each time:

```sh
cd frontend/assets/flight-map-3d
npm install
npm run dev
```

Run `npm run dev -- --host 127.0.0.1` and open
`http://127.0.0.1:5173`. The standalone scene is a renderer; Flutter owns
scenario selection and status panels. For a standalone scenario, add a query
parameter such as `?scenario=storm-wall`.

### 3. Flutter app (production path)

The Flutter app loads a **bundled, pre-built** copy of the Three.js scene as
a WebView asset — it does not run a dev server. Build the scene before
running Flutter:

```sh
cd frontend/assets/flight-map-3d
npm install
npm run build
cd ../../..
flutter run
```

The Vite build uses relative asset URLs specifically so it loads correctly
from Flutter's asset bundle rather than requiring a live server at runtime.
**Re-run `npm run build` any time the Three.js source changes** — Flutter
will keep serving the old build otherwise.

---

## Flight corridor & grid configuration

| Parameter               | Value                                                                                                                   |
| ----------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| Origin                  | Craiova (LCCR) — 44.3180°N, 23.8886°E                                                                                   |
| Destination             | Cluj-Napoca (LRCL) — 46.783389°N, 23.684194°E                                                                           |
| Straight-line distance  | ~275 km                                                                                                                 |
| Grid envelope           | lat 43.5°–48.5°, lon 19.5°–30.0°; weather points are masked to Romania                                               |
| Grid resolution         | 0.5° steps → 242 rectangular candidates, about 136 after the country mask                                              |
| Pressure levels         | 500, 400, 300, 250, 200 hPa                                                                                             |
| Total grid nodes        | About 136 × 5 = 680 for a full synthetic scene                                                                          |
| Forecast cadence        | 6-hour steps (native AIFS resolution — UI must show actual forecast-valid timestamps, never implies hourly granularity) |
| Weather cache TTL       | 6 hours, matched to forecast step                                                                                       |
| Default cruise altitude | 250 hPa (10.4 km)                                                                                                       |
| Vertical exaggeration   | 4×                                                                                                                       |
| CJ3 max cruise speed    | 416 kt / 770.4 km/h                                                                                                     |

## Aircraft model and route separation

Scenarios use the original Cessna Citation CJ3 reference profile. Nominal
reference figures included in the backend payload are 14,000 lb ramp mass,
13,870 lb maximum takeoff mass, 12,750 lb maximum landing mass, 4,710 lb
maximum usable fuel, 45,000 ft service ceiling, and 2,040 nm published range.
The scenario gross-mass default uses maximum takeoff mass. Fuel flow
(520 kg/h), descent rate, and route fuel estimates are simulation assumptions,
not POH/AFM or dispatch data; aircraft-specific limits vary by serial number
and installed equipment. Do not use this prototype for flight planning.

Multi-flight synthetic scenarios plan optimized routes sequentially and reserve
each route against later A* searches. En-route centerlines are kept at least
0.05 km apart in modeled 3D geometry; takeoff and landing segments are excluded
to allow shared airport terminals. This visualization constraint is not an
operational separation or collision-avoidance system.

---

## Coordinate system

All geographic positions are converted once, backend-side, into a local flat
scene coordinate system — the frontend never performs geographic math.

- **Origin (0,0,0):** 45.625°N, 24.875°E (center of the active grid)
- **X** = east/west offset (km)
- **Y** = altitude, with **4x vertical exaggeration** (otherwise the ~4.6 km
  altitude span is invisible against the ~400 km horizontal span)
- **Z** = north/south offset (km)
- 1 scene unit = 1 km

Longitude distance is scaled by `cos(origin_latitude)` since meters-per-degree
longitude shrinks with latitude; meters-per-degree latitude (111.32 km) is
constant everywhere. This conversion lives in exactly one place —
`grid/coordinates.py` — and is applied to grid cells, storm event centroids,
route waypoints, and airport markers. Three.js uses those backend coordinates
for rendering and converts a picked scene point back to geographic coordinates
only for route inspection; the frontend does not plan or replan routes.

---

## Weather exposure score

Each grid cell gets a single 0–100 score:

```
R = 0.35·CAPE + 0.25·Precipitation + 0.20·|VerticalVelocity| + 0.10·Humidity + 0.10·CloudCover
```

All components are normalized to [0,1] before weighting. **Missing
components are excluded and remaining weights are renormalized — never
treated as zero risk.** Display bands (illustrative only, not certified
aviation thresholds):

## Storm event detection

Adjacent cells crossing severity thresholds are merged into discrete labeled
events (`rain`, `thunderstorm`, `severe_storm`) via connected-component
labeling (`scipy.ndimage.label`), each reported with a centroid position and
cell count. This is a **coarse proxy from ~28km-resolution forecast data**,
not radar nowcasting — it cannot and does not claim to detect tornado-scale
circulation.

## Route optimization (A\*)

A\* searches the 3D grid (26-directional connectivity: 8 same-layer + 9 above
Heuristic: straight-line distance ÷ cruise speed (admissible — never
overestimates true remaining cost). The baseline is a separate straight
airport-to-airport reference with modeled takeoff, climb, cruise, and landing
phases; it is not used for pathfinding.

---

## API reference

All POST endpoints accept optional grid-bound overrides
(`min_lat/max_lat/min_lon/max_lon/lat_step/lon_step`) and `test_mode: bool`.
Omit overrides to use the locked corridor config above.

| Endpoint          | Method | Purpose                                                          |
| ----------------- | ------ | ---------------------------------------------------------------- |
| `/health`         | GET    | Liveness check                                                   |
| `/weather-grid`   | POST   | Fetch/build the weather grid for given (or default) bounds       |
| `/weather-events` | POST   | Detect storm clusters; `test_mode:true` limits to the 2 airports |
| `/optimize`       | POST   | Real A\*-powered route optimization;                             |
| `/test-scene-data`| POST   | Full live weather scene, routes, airports, and metadata          |
| `/replan`         | POST   | Reassess route against updated weather and replan when needed     |
| `/test-scenarios/{scenario}` | GET | Synthetic demo scene or external `real-meteo` forecast  |

### Synthetic weather scenarios

Synthetic IDs include `crossroads-storm`, `converge-bucharest`,
`carpathian-siege`, `random-storms`, `heavy-storms`, `layered-random`,
`clear-airspace`, `storm-wall`, `over-the-top`, `low-corridor`, `slalom`,
`fuel-critical`, and `in-flight-replan`. They do not call Open-Meteo and are
deterministic for a given seed. `drastic-weather-change` remains a compatible
alias for the in-flight scenario. `real-meteo` is not synthetic: it depends on
the external Open-Meteo service and reports provider errors rather than
pretending generated data is live weather.

The Flutter shell owns scenario selection, camera and layer controls, status,
metrics, telemetry, and route inspection. It loads the packaged scene from
`assets/flight-map-3d/dist/build/` and communicates through the versioned
protocol in [BRIDGE_PROTOCOL.md](./frontend/assets/flight-map-3d/BRIDGE_PROTOCOL.md).
The backend remains the sole owner of weather normalization and route
planning.

---

## Response payload contract

Returned by `/test-scene-data`, `/optimize`, and all `/test-scenarios/*`
endpoints:

```
meta:     { source, fetched_at, origin_lat, origin_lon, scene_unit,
            vertical_exaggeration, trajectory_status? }
grid:     [ { lat, lon, forecast_time, cape, precipitation, cloud_cover, x, z,
              levels: { "<pressure>": { temperature, wind_speed, wind_direction,
                         geopotential_height, exposure_score, altitude_km, y } } } ]
events:   [ { type, level_hpa, centroid: {lat,lon,x,y,z}, cell_count, bounding_box } ]
airports: [ { name, lat, lon, x, y, z } ]
routes:   { baseline: [ {lat,lon,x,y,z,exposure_score}, ... ],
            optimized: [ same shape ],
            metrics: { baseline: {distance_km,time_min,avg_exposure},
                       optimized: {...} } }
flights:  optional multi-flight list; each item contains id, routes, and metrics
```

Synthetic scenario events may be compact type/cell-count summaries; live
weather events include cluster details. Any forecast field may be `null` when
the provider omits it. The scene and Flutter UI must preserve nulls instead of
substituting invented weather or aircraft data.

The scene emits telemetry values that are based on the backend's modeled
aircraft profile and route metrics, not live aircraft sensors. On physical
phones, configure a reachable backend URL in Flutter (or with
`--dart-define=AIRSPACE_API_BASE=...`); the Android emulator default
`10.0.2.2` does not work on a physical device.

---

## Testing

```sh
cd backend
pip install -r requirements-dev.txt
python -m pytest -v --basetemp=.pytest-temp
```

All tests run against mocked network calls and temporary cache paths — no
test hits the real Open-Meteo API. Key regressions guarded against:
missing-data renormalization in the exposure score, correct adjacency
merging in storm clustering, and coordinate-origin correctness.
