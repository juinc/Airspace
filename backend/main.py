from datetime import datetime, timezone
from typing import Optional

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from weather.client import fetch_forecast, parse_response, PRESSURE_LEVELS
from weather.cache import load_cache, save_cache
from weather.events import detect_events
from grid.builder import build_horizontal_grid
from grid.coordinates import (
    attach_scene_coordinates,
    latlon_to_scene_xz,
    GRID_ORIGIN_LAT,
    GRID_ORIGIN_LON,
    VERTICAL_EXAGGERATION,
)
from optimizer.stub_trajectory import generate_stub_route, compute_route_metrics

app = FastAPI(title="Airspace Weather Backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://10.0.2.2:5173",
    ],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

DEFAULT_CONFIG = {
    "min_lat": 43.75,
    "max_lat": 47.50,
    "min_lon": 22.75,
    "max_lon": 27.00,
    "lat_step": 0.25,
    "lon_step": 0.25,
}

ROMANIA_MAP_GEO_BOUNDS = {
    "min_lat": 43.6186,
    "max_lat": 48.2656,
    "min_lon": 20.2617,
    "max_lon": 29.6917,
}

ROUTE = {
    "origin": {"name": "LCCR", "city": "Craiova", "lat": 44.3180, "lon": 23.8886},
    "destination": {"name": "LRCL", "city": "Cluj-Napoca", "lat": 46.783389, "lon": 23.684194},
}


def _scene_airports():
    airports = []
    for airport in ROUTE.values():
        x, z = latlon_to_scene_xz(airport["lat"], airport["lon"])
        airports.append({
            "name": f"{airport['name']} {airport['city']}",
            "lat": airport["lat"],
            "lon": airport["lon"],
            "x": x,
            "y": 0.0,
            "z": z,
        })
    return airports


def _scene_map_bounds():
    min_x, min_z = latlon_to_scene_xz(
        ROMANIA_MAP_GEO_BOUNDS["min_lat"], ROMANIA_MAP_GEO_BOUNDS["min_lon"]
    )
    max_x, max_z = latlon_to_scene_xz(
        ROMANIA_MAP_GEO_BOUNDS["max_lat"], ROMANIA_MAP_GEO_BOUNDS["max_lon"]
    )
    return {"min_x": min_x, "max_x": max_x, "min_z": min_z, "max_z": max_z}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/test-weather")
def test_weather():
    lat_list = [ROUTE["origin"]["lat"], ROUTE["destination"]["lat"]]
    lon_list = [ROUTE["origin"]["lon"], ROUTE["destination"]["lon"]]

    cache_key = "test-weather"
    cached = load_cache(cache_key)
    if cached:
        return {"source": "cache", "data": cached}

    raw = fetch_forecast(lat_list, lon_list)
    results = parse_response(raw, lat_list, lon_list, PRESSURE_LEVELS)
    results = attach_scene_coordinates(results, PRESSURE_LEVELS)   # ← new line

    save_cache(cache_key, results)
    return {
        "source": "live",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "data": results,
    }


class GridRequest(BaseModel):
    min_lat: Optional[float] = None
    max_lat: Optional[float] = None
    min_lon: Optional[float] = None
    max_lon: Optional[float] = None
    lat_step: Optional[float] = None
    lon_step: Optional[float] = None
    test_mode: bool = True


@app.post("/weather-grid")
def weather_grid(req: GridRequest):
    """
    With test_mode=True, only fetches 4 points.
    """
    overrides = {k: v for k, v in req.dict().items() if v is not None and k != "test_mode"}
    cfg = {**DEFAULT_CONFIG, **overrides}
        
    try:
        points = build_horizontal_grid(
            cfg["min_lat"], cfg["max_lat"],
            cfg["min_lon"], cfg["max_lon"],
            cfg["lat_step"], cfg["lon_step"],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if req.test_mode:
        points = points[:4]

    cache_key = f"grid-{len(points)}-{cfg['lat_step']}"
    cached = load_cache(cache_key)
    if cached:
        return {"source": "cache", "point_count": len(points), "data": cached}

    lat_list = [p["lat"] for p in points]
    lon_list = [p["lon"] for p in points]

    raw = fetch_forecast(lat_list, lon_list)
    results = parse_response(raw, lat_list, lon_list, PRESSURE_LEVELS)

    save_cache(cache_key, results)

    return {
        "source": "live",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "point_count": len(points),
        "scene_config": {
            "origin_lat": GRID_ORIGIN_LAT,
            "origin_lon": GRID_ORIGIN_LON,
            "scene_unit": "km",
            "vertical_exaggeration": VERTICAL_EXAGGERATION,
        },
        "data": results,
    }


@app.post("/weather-events")
def weather_events(req: GridRequest):
    cfg = {**DEFAULT_CONFIG, **{k: v for k, v in req.dict().items() if v is not None and k != "test_mode"}}

    if req.test_mode:
        # quick check: just the two route endpoints, not the full grid
        lat_list = [ROUTE["origin"]["lat"], ROUTE["destination"]["lat"]]
        lon_list = [ROUTE["origin"]["lon"], ROUTE["destination"]["lon"]]
        lat_values = lat_list
        lon_values = lon_list
        n_lats, n_lons = 2, 1  # 2 separate single-column "rows" — no adjacency between them
    else:
        lat_values = list(np.arange(cfg["min_lat"], cfg["max_lat"] + cfg["lat_step"] / 2, cfg["lat_step"]))
        lon_values = list(np.arange(cfg["min_lon"], cfg["max_lon"] + cfg["lon_step"] / 2, cfg["lon_step"]))
        try:
            points = build_horizontal_grid(cfg["min_lat"], cfg["max_lat"], cfg["min_lon"], cfg["max_lon"],
                                        cfg["lat_step"], cfg["lon_step"])
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        
        lat_list = [p["lat"] for p in points]
        lon_list = [p["lon"] for p in points]
        n_lats, n_lons = len(lat_values), len(lon_values)

    raw = fetch_forecast(lat_list, lon_list)
    results = parse_response(raw, lat_list, lon_list, PRESSURE_LEVELS)
    results = attach_scene_coordinates(results, PRESSURE_LEVELS)

    all_events = []
    for level in PRESSURE_LEVELS:
        for label in ("rain", "thunderstorm", "severe_storm"):
            all_events.extend(
                detect_events(results, n_lats, n_lons, lat_values, lon_values, level, label)
            )

    return {"events": all_events, "checked_points": results}

@app.post("/test-scene-data")
def test_scene_data(req: GridRequest):
    """
    TEMPORARY endpoint for frontend development. Returns the full contract
    shape — grid, events, baseline/optimized routes, metrics — using the
    real weather pipeline but a STUBBED trajectory (not real A*).
    """
    cfg = {**DEFAULT_CONFIG, **{k: v for k, v in req.dict().items() if v is not None and k != "test_mode"}}

    cache_key = f"test-scene-{cfg['lat_step']}"
    cached = load_cache(cache_key)
    if cached and not req.test_mode:
        cached.setdefault("airports", _scene_airports())
        cached.setdefault("meta", {}).setdefault("map_bounds", _scene_map_bounds())
        return cached

    try:
        points = build_horizontal_grid(cfg["min_lat"], cfg["max_lat"], cfg["min_lon"], cfg["max_lon"],
                                        cfg["lat_step"], cfg["lon_step"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    if req.test_mode:
        points = points[:36]  # smaller subset = faster iteration while frontend is building

    lat_list = [p["lat"] for p in points]
    lon_list = [p["lon"] for p in points]

    raw = fetch_forecast(lat_list, lon_list)
    grid_results = parse_response(raw, lat_list, lon_list, PRESSURE_LEVELS)
    grid_results = attach_scene_coordinates(grid_results, PRESSURE_LEVELS)

    lat_values = sorted(set(p["lat"] for p in points))
    lon_values = sorted(set(p["lon"] for p in points))

    all_events = []
    for level in PRESSURE_LEVELS:
        for label in ("rain", "thunderstorm", "severe_storm"):
            all_events.extend(
                detect_events(grid_results, len(lat_values), len(lon_values), lat_values, lon_values, level, label)
            )

    baseline_route = generate_stub_route(ROUTE["origin"], ROUTE["destination"], grid_results, lateral_offset_km=0.0, altitude_offset_km=0.0)
    optimized_route = generate_stub_route(ROUTE["origin"], ROUTE["destination"], grid_results, lateral_offset_km=40.0, altitude_offset_km=1.0)

    payload = {
        "meta": {
            "source": "live",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "origin_lat": GRID_ORIGIN_LAT,
            "origin_lon": GRID_ORIGIN_LON,
            "scene_unit": "km",
            "vertical_exaggeration": VERTICAL_EXAGGERATION,
            "map_bounds": _scene_map_bounds(),
            "trajectory_status": "STUB - not real A*, for contract testing only",
        },
        "grid": grid_results,
        "events": all_events,
        "airports": _scene_airports(),
        "routes": {
            "baseline": baseline_route,
            "optimized": optimized_route,
            "metrics": {
                "baseline": compute_route_metrics(baseline_route),
                "optimized": compute_route_metrics(optimized_route),
            },
        },
    }

    if not req.test_mode:
        save_cache(cache_key, payload)

    return payload