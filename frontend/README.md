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
┌─────────────────────┐        JSON over HTTP        ┌──────────────────────┐
│   Flutter App        │ ───────────────────────────▶ │  FastAPI Backend      │
│   (webview_flutter)  │ ◀─────────────────────────── │  (Python)             │
└──────────┬───────────┘                               └───────────┬──────────┘
           │ loads bundled                                         │ fetches
           │ Vite build                                            ▼
           ▼                                              ┌──────────────────┐
┌─────────────────────┐                                   │  Open-Meteo API   │
│  Three.js Scene       │                                 │  (ECMWF AIFS)      │
│  (grid, events,       │                                 └──────────────────┘
│   routes, airports)   │
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

Open `http://localhost:5173`. The scenario selector defaults to **"A lot
more storms"** (see [Synthetic Weather Scenarios](#synthetic-weather-scenarios)
below).

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
| Grid bounds             | lat 43.75°–47.50°, lon 22.75°–27.00°                                                                                    |
| Grid resolution         | 0.25° steps → 16 × 18 = 288 horizontal points                                                                           |
| Pressure levels         | 400, 300, 250, 200 hPa (≈7.2 / 9.2 / 10.4 / 11.8 km)                                                                    |
| Total grid nodes        | 288 × 4 = 1,152                                                                                                         |
| Forecast cadence        | 6-hour steps (native AIFS resolution — UI must show actual forecast-valid timestamps, never implies hourly granularity) |
| Cache TTL               | 6 hours, matched to forecast step                                                                                       |
| Default cruise altitude | 250 hPa (10.4 km)                                                                                                       |
| Assumed cruise speed    | 800 km/h                                                                                                                |

---

## Coordinate system

All geographic positions are converted once, backend-side, into a local flat
scene coordinate system — the frontend never performs geographic math.

- **Origin (0,0,0):** 45.625°N, 24.875°E (center of the active grid)
- **X** = east/west offset (km)
- **Y** = altitude, with **20x vertical exaggeration** (otherwise the ~4.6 km
  altitude span is invisible against the ~400 km horizontal span)
- **Z** = north/south offset (km)
- 1 scene unit = 1 km

Longitude distance is scaled by `cos(origin_latitude)` since meters-per-degree
longitude shrinks with latitude; meters-per-degree latitude (111.32 km) is
constant everywhere. This conversion lives in exactly one place —
`grid/coordinates.py` — and is applied identically to grid cells, storm event
centroids, route waypoints, and airport markers. No other module and no
frontend code performs this conversion independently.

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
overestimates true remaining cost). The baseline/direct route is a separate,
non-weather-aware straight line at default cruise altitude, used purely as a
comparison reference.

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

### Synthetic weather scenarios

The `/test-scenarios/*` endpoints return **fully synthetic, reproducible**
JSON — they do not call Open-Meteo and are intended for demoing and testing
how the optimizer and scene respond to different weather conditions on
demand, without depending on whatever the real atmosphere happens to be
doing on demo day. The Three.js scene's scenario selector defaults to **"A
lot more storms"** specifically because it's the most visually compelling
proof of the core claim: that the optimized route visibly bends around
weather. Any payload returned by these endpoints — synthetic or real — must
follow the identical response contract described below; the frontend cannot
tell (and does not need to tell) the difference.

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
```

Any field may be `null` if the forecast omitted that variable. The frontend
must skip rendering that element rather than defaulting it to a "safe" value.

---

## Testing

```sh
cd backend
pip install -r requirements-dev.txt
pytest -v
```

All tests run against mocked network calls and temporary cache paths — no
test hits the real Open-Meteo API. Key regressions guarded against:
missing-data renormalization in the exposure score, correct adjacency
merging in storm clustering, and coordinate-origin correctness.
