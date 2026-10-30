from datetime import datetime, timezone
from typing import Optional

import numpy as np
from fastapi import FastAPI
from pydantic import BaseModel

from weather.client import fetch_forecast, parse_response, PRESSURE_LEVELS
from weather.cache import load_cache, save_cache
from weather.events import detect_events
from grid.builder import build_horizontal_grid

app = FastAPI(title="Airspace Weather Backend")

DEFAULT_CONFIG = {
    "min_lat": 43.75,
    "max_lat": 47.50,
    "min_lon": 22.75,
    "max_lon": 27.00,
    "lat_step": 0.25,
    "lon_step": 0.25,
}

ROUTE = {
    "origin": {"name": "LROP", "lat": 44.572161, "lon": 26.102218},
    "destination": {"name": "LRCL", "lat": 46.783389, "lon": 23.684194},
}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/test-weather")
def test_weather():
    """
    STEP 1 OF TESTING: run this first.
    Fetches real forecast data for just the two airports (2 points).
    """
    lat_list = [ROUTE["origin"]["lat"], ROUTE["destination"]["lat"]]
    lon_list = [ROUTE["origin"]["lon"], ROUTE["destination"]["lon"]]

    cache_key = "test-weather"
    cached = load_cache(cache_key)
    if cached:
        return {"source": "cache", "data": cached}

    raw = fetch_forecast(lat_list, lon_list)
    results = parse_response(raw, lat_list, lon_list, PRESSURE_LEVELS)

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
    STEP 2 OF TESTING: run this after /test-weather works.
    With test_mode=True, only fetches 4 points.
    """
    overrides = {k: v for k, v in req.dict().items() if v is not None and k != "test_mode"}
    cfg = {**DEFAULT_CONFIG, **overrides}

    points = build_horizontal_grid(
        cfg["min_lat"], cfg["max_lat"],
        cfg["min_lon"], cfg["max_lon"],
        cfg["lat_step"], cfg["lon_step"],
    )

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
        "data": results,
    }


@app.post("/weather-events")
def weather_events(req: GridRequest):
    """
    STEP 3: detects discrete rain/thunderstorm/severe_storm clusters
    across the full configured grid (ignores test_mode — always full grid).
    """
    cfg = {**DEFAULT_CONFIG, **{k: v for k, v in req.dict().items() if v is not None and k != "test_mode"}}

    lat_values = list(np.arange(cfg["min_lat"], cfg["max_lat"] + cfg["lat_step"] / 2, cfg["lat_step"]))
    lon_values = list(np.arange(cfg["min_lon"], cfg["max_lon"] + cfg["lon_step"] / 2, cfg["lon_step"]))

    points = build_horizontal_grid(
        cfg["min_lat"], cfg["max_lat"],
        cfg["min_lon"], cfg["max_lon"],
        cfg["lat_step"], cfg["lon_step"],
    )

    lat_list = [p["lat"] for p in points]
    lon_list = [p["lon"] for p in points]

    raw = fetch_forecast(lat_list, lon_list)
    results = parse_response(raw, lat_list, lon_list, PRESSURE_LEVELS)

    all_events = []
    for level in PRESSURE_LEVELS:
        for label in ("rain", "thunderstorm", "severe_storm"):
            all_events.extend(
                detect_events(results, len(lat_values), len(lon_values), lat_values, lon_values, level, label)
            )

    return {"events": all_events}