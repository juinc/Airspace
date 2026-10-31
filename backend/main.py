from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from requests import RequestException

from weather.client import (
    FORECAST_DAYS,
    FORECAST_STEP_HOURS,
    OPEN_METEO_MODEL,
    PRESSURE_LEVELS,
    build_variable_list,
    fetch_forecast,
    parse_response,
    select_forecast_index,
)
from weather.cache import build_cache_key, load_cache, save_cache
from weather.events import detect_events
from grid.builder import build_horizontal_grid
from grid.coordinates import (
    attach_scene_coordinates,
    latlon_to_scene_xz,
    GRID_ORIGIN_LAT,
    GRID_ORIGIN_LON,
    VERTICAL_EXAGGERATION,
)
from optimizer.astar import (
    ALTITUDE_CHANGE_PENALTY_MIN,
    BASELINE_PRESSURE_LEVEL,
    CRUISE_SPEED_KMH,
    WEATHER_WEIGHTS,
    compute_route_metrics,
    assess_route_weather_change,
    estimate_route_position,
    find_avoided_high_exposure_cells,
    find_path,
    normalize_mode,
)
from optimizer.stub_trajectory import generate_baseline_route
from synthetic_scenarios import (
    SCENARIO_TITLES,
    build_synthetic_events,
    build_synthetic_grid,
    build_synthetic_routes,
)

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


def _forecast_cache_key(points):
    return build_cache_key(
        "open-meteo-aifs-raw-v2",
        model=OPEN_METEO_MODEL,
        variables=build_variable_list(),
        pressure_levels=PRESSURE_LEVELS,
        forecast_days=FORECAST_DAYS,
        forecast_step_hours=FORECAST_STEP_HOURS,
        timezone=["GMT"] * len(points),
        coordinates=[(point["lat"], point["lon"]) for point in points],
    )


def _fetch_weather(points, force_refresh=False):
    key = _forecast_cache_key(points)
    raw = None if force_refresh else load_cache(key)
    source = "live" if force_refresh else "cache"
    if raw is None:
        latitudes = [point["lat"] for point in points]
        longitudes = [point["lon"] for point in points]
        try:
            raw = fetch_forecast(latitudes, longitudes)
        except RequestException as error:
            raise HTTPException(
                status_code=502,
                detail=f"Weather provider request failed: {error}",
            ) from error
        save_cache(key, raw)
        source = "live"

    try:
        forecast_index = select_forecast_index(raw)
    except ValueError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    latitudes = [point["lat"] for point in points]
    longitudes = [point["lon"] for point in points]
    results = parse_response(
        raw,
        latitudes,
        longitudes,
        PRESSURE_LEVELS,
        forecast_index=forecast_index,
    )
    return results, source


def _forecast_metadata(grid_results):
    valid_times = sorted(
        {
            point["forecast_time"]
            for point in grid_results
            if point.get("forecast_time") is not None
        }
    )
    metadata = {
        "weather_model": OPEN_METEO_MODEL,
        "forecast_step_hours": FORECAST_STEP_HOURS,
    }
    if len(valid_times) == 1:
        metadata["forecast_valid_time"] = valid_times[0]
    elif valid_times:
        metadata["forecast_valid_times"] = valid_times
    return metadata


def _routing_assumptions():
    return {
        "cruise_speed_kmh": CRUISE_SPEED_KMH,
        "baseline_pressure_level_hpa": BASELINE_PRESSURE_LEVEL,
        "altitude_change_penalty_min": ALTITUDE_CHANGE_PENALTY_MIN,
        "climb_descent_model": "constant_cruise_speed",
        "terrain_clearance_validated": False,
        "weather_hard_exclusion": False,
        "exposure_bands_are_advisory": True,
        "weather_weights": dict(WEATHER_WEIGHTS),
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/test-weather")
def test_weather():
    points = [
        {"lat": airport["lat"], "lon": airport["lon"]}
        for airport in ROUTE.values()
    ]
    results, source = _fetch_weather(points)
    results = attach_scene_coordinates(results, PRESSURE_LEVELS)   # ← new line
    return {
        "source": source,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        **_forecast_metadata(results),
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
    mode: str = "Balanced"


class OptimizeRequest(GridRequest):
    test_mode: bool = False


class ReplanRequest(BaseModel):
    mode: str = "Balanced"
    route_progress: float = Field(default=0.35, ge=0, le=1)
    weather_seed: int = 0
    previous_grid: list[dict]
    previous_route: list[dict]
    previous_source: str = "synthetic"
    grid_config: dict = Field(default_factory=dict)


def _scene_grid(req, force_refresh=False):
    overrides = {
        key: value
        for key, value in req.model_dump().items()
        if value is not None and key not in {"test_mode", "mode"}
    }
    cfg = {**DEFAULT_CONFIG, **overrides}
    try:
        points = build_horizontal_grid(
            cfg["min_lat"],
            cfg["max_lat"],
            cfg["min_lon"],
            cfg["max_lon"],
            cfg["lat_step"],
            cfg["lon_step"],
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))

    if req.test_mode:
        points = points[:36]

    grid_results, source = _fetch_weather(points, force_refresh=force_refresh)
    return cfg, attach_scene_coordinates(grid_results, PRESSURE_LEVELS), source


def _scene_routes(grid_results, mode):
    optimized_route = find_path(
        grid_results, ROUTE["origin"], ROUTE["destination"], mode=mode
    )
    baseline_route = generate_baseline_route(
        ROUTE["origin"],
        ROUTE["destination"],
        grid_results,
        num_points=max(1, len(optimized_route) - 1),
    )
    canonical_mode = normalize_mode(mode)
    return {
        "baseline": baseline_route,
        "optimized": optimized_route,
        "metrics": {
            "baseline": compute_route_metrics(baseline_route),
            "optimized": compute_route_metrics(optimized_route),
        },
        "reasoning": {
            "mode": canonical_mode,
            "avoided_high_exposure_cells": find_avoided_high_exposure_cells(
                grid_results, baseline_route, optimized_route
            ),
        },
    }


@app.post("/weather-grid")
def weather_grid(req: GridRequest):
    """
    With test_mode=True, only fetches 4 points.
    """
    overrides = {
        k: v
        for k, v in req.model_dump().items()
        if v is not None and k not in {"test_mode", "mode"}
    }
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

    results, source = _fetch_weather(points)

    return {
        "source": source,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "point_count": len(points),
        **_forecast_metadata(results),
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
    cfg = {
        **DEFAULT_CONFIG,
        **{
            k: v
            for k, v in req.model_dump().items()
            if v is not None and k not in {"test_mode", "mode"}
        },
    }

    if req.test_mode:
        # quick check: just the two route endpoints, not the full grid
        points = [
            {"lat": airport["lat"], "lon": airport["lon"]}
            for airport in ROUTE.values()
        ]
    else:
        try:
            points = build_horizontal_grid(cfg["min_lat"], cfg["max_lat"], cfg["min_lon"], cfg["max_lon"],
                                        cfg["lat_step"], cfg["lon_step"])
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    lat_values = sorted({point["lat"] for point in points})
    lon_values = sorted({point["lon"] for point in points})
    n_lats = len(points) if req.test_mode else len(lat_values)
    n_lons = 1 if req.test_mode else len(lon_values)
    results, source = _fetch_weather(points)
    results = attach_scene_coordinates(results, PRESSURE_LEVELS)

    all_events = []
    for level in PRESSURE_LEVELS:
        for label in ("rain", "thunderstorm", "severe_storm"):
            all_events.extend(
                detect_events(results, n_lats, n_lons, lat_values, lon_values, level, label)
            )

    return {"source": source, **_forecast_metadata(results), "events": all_events, "checked_points": results}

@app.post("/test-scene-data")
def test_scene_data(req: GridRequest):
    """
    Returns the full scene contract with a weather-aware A* optimized route.
    """
    try:
        mode = normalize_mode(req.mode)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))

    cfg = {
        **DEFAULT_CONFIG,
        **{
            key: value
            for key, value in req.model_dump().items()
            if value is not None and key not in {"test_mode", "mode"}
        },
    }

    _, grid_results, weather_source = _scene_grid(req)
    forecast_valid_times = sorted(
        {
            point["forecast_time"]
            for point in grid_results
            if point.get("forecast_time") is not None
        }
    )
    cache_key = build_cache_key(
        "full-aifs-scene",
        config=cfg,
        mode=mode,
        model=OPEN_METEO_MODEL,
        variables=build_variable_list(),
        pressure_levels=PRESSURE_LEVELS,
        forecast_days=FORECAST_DAYS,
        forecast_valid_times=forecast_valid_times,
        route=ROUTE,
    )
    cached = load_cache(cache_key)
    if cached and not req.test_mode:
        cached.setdefault("airports", _scene_airports())
        cached_meta = cached.setdefault("meta", {})
        cached_meta["source"] = "cache"
        cached_meta.setdefault("map_bounds", _scene_map_bounds())
        return cached

    lat_values = sorted(set(point["lat"] for point in grid_results))
    lon_values = sorted(set(point["lon"] for point in grid_results))

    all_events = []
    for level in PRESSURE_LEVELS:
        for label in ("rain", "thunderstorm", "severe_storm"):
            all_events.extend(
                detect_events(grid_results, len(lat_values), len(lon_values), lat_values, lon_values, level, label)
            )

    try:
        routes = _scene_routes(grid_results, mode)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))

    payload = {
        "meta": {
            "source": weather_source,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            **_forecast_metadata(grid_results),
            "origin_lat": GRID_ORIGIN_LAT,
            "origin_lon": GRID_ORIGIN_LON,
            "scene_unit": "km",
            "vertical_exaggeration": VERTICAL_EXAGGERATION,
            "map_bounds": _scene_map_bounds(),
            "grid_config": cfg,
            "routing_assumptions": _routing_assumptions(),
            "trajectory_status": f"A* optimized route ({mode})",
        },
        "grid": grid_results,
        "events": all_events,
        "airports": _scene_airports(),
        "routes": routes,
    }

    if not req.test_mode:
        save_cache(cache_key, payload)

    return payload


@app.post("/optimize")
def optimize(req: OptimizeRequest):
    """Return baseline and A* routes for the selected weather preference."""
    try:
        mode = normalize_mode(req.mode)
        _, grid_results, _ = _scene_grid(req)
        return _scene_routes(grid_results, mode)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))


@app.post("/replan")
def replan(req: ReplanRequest):
    try:
        mode = normalize_mode(req.mode)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    if req.previous_source == "synthetic":
        config = {**DEFAULT_CONFIG, **req.grid_config}
        updated_grid = build_synthetic_grid(
            "drastic-weather-change",
            config,
            weather_seed=req.weather_seed,
        )
        source = "synthetic"
    else:
        config = {**DEFAULT_CONFIG, **req.grid_config}
        grid_request = GridRequest(**config, test_mode=False, mode=mode)
        _, updated_grid, source = _scene_grid(grid_request)

    return _weather_replan_payload(
        req.previous_grid,
        req.previous_route,
        req.route_progress,
        mode,
        updated_grid,
        source,
        "drastic-weather-change",
        req.weather_seed,
    )


@app.get("/test-scenarios/{scenario}")
def test_scenario(
    scenario: str,
    mode: str = "Balanced",
    route_progress: float = 0.35,
    weather_seed: int = 0,
):
    """Return a synthetic scenario or a live Open-Meteo scene."""
    if scenario == "real-meteo":
        payload = test_scene_data(GridRequest(test_mode=False, mode=mode))
        meta = payload.setdefault("meta", {})
        meta["scenario"] = scenario
        meta["scenario_title"] = "Open-Meteo forecast"
        return payload

    if scenario == "drastic-weather-change":
        if not 0 <= route_progress <= 1:
            raise HTTPException(status_code=400, detail="route_progress must be between 0 and 1")
        try:
            previous_grid = build_synthetic_grid("clear-airspace", DEFAULT_CONFIG)
            previous_routes = build_synthetic_routes(previous_grid, ROUTE, mode)
            updated_grid = build_synthetic_grid(
                scenario,
                DEFAULT_CONFIG,
                weather_seed=weather_seed,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return _weather_replan_payload(
            previous_grid,
            previous_routes["optimized"],
            route_progress,
            mode,
            updated_grid,
            "synthetic",
            scenario,
            weather_seed,
        )

    try:
        grid = build_synthetic_grid(scenario, DEFAULT_CONFIG)
        routes = build_synthetic_routes(grid, ROUTE, mode)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))

    events = build_synthetic_events(grid)
    return {
        "meta": {
            "source": "synthetic",
            "scenario": scenario,
            "scenario_title": SCENARIO_TITLES[scenario],
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "origin_lat": GRID_ORIGIN_LAT,
            "origin_lon": GRID_ORIGIN_LON,
            "scene_unit": "km",
            "vertical_exaggeration": VERTICAL_EXAGGERATION,
            "map_bounds": _scene_map_bounds(),
            "grid_config": DEFAULT_CONFIG,
            "routing_assumptions": _routing_assumptions(),
            "trajectory_status": f"Synthetic A* route ({routes['reasoning']['mode']})",
        },
        "grid": grid,
        "events": events,
        "airports": _scene_airports(),
        "routes": routes,
    }


def _weather_replan_payload(
    previous_grid,
    previous_route,
    route_progress,
    mode,
    updated_grid,
    source,
    scenario,
    weather_seed=0,
):
    if len(previous_route) < 2:
        raise HTTPException(status_code=400, detail="previous_route needs at least two waypoints")
    try:
        canonical_mode = normalize_mode(mode)
        resume_position = estimate_route_position(previous_route, route_progress)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    weather_change = assess_route_weather_change(
        previous_grid, updated_grid, previous_route, route_progress
    )
    if weather_change["drastic"]:
        optimized_route = find_path(
            updated_grid,
            ROUTE["origin"],
            ROUTE["destination"],
            mode=canonical_mode,
            start_position=resume_position,
        )
        trajectory_status = f"A* replanned from {route_progress:.0%} route progress"
    else:
        optimized_route = previous_route
        trajectory_status = "Weather change below drastic threshold; keeping current route"

    baseline_route = generate_baseline_route(
        ROUTE["origin"],
        ROUTE["destination"],
        updated_grid,
        num_points=max(1, len(optimized_route) - 1),
    )
    routes = {
        "baseline": baseline_route,
        "previous_optimized": previous_route,
        "optimized": optimized_route,
        "metrics": {
            "baseline": compute_route_metrics(baseline_route),
            "optimized": compute_route_metrics(optimized_route),
        },
        "reasoning": {
            "mode": canonical_mode,
            "weather_change": weather_change,
            "avoided_high_exposure_cells": find_avoided_high_exposure_cells(
                updated_grid, baseline_route, optimized_route
            ),
        },
    }
    valid_times = _forecast_metadata(updated_grid)
    return {
        "meta": {
            "source": source,
            "scenario": scenario,
            "scenario_title": "Drastic weather change and in-flight replan",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            **valid_times,
            "origin_lat": GRID_ORIGIN_LAT,
            "origin_lon": GRID_ORIGIN_LON,
            "scene_unit": "km",
            "vertical_exaggeration": VERTICAL_EXAGGERATION,
            "map_bounds": _scene_map_bounds(),
            "grid_config": DEFAULT_CONFIG,
            "routing_assumptions": _routing_assumptions(),
            "trajectory_status": trajectory_status,
        },
        "grid": updated_grid,
        "events": build_synthetic_events(updated_grid)
        if source == "synthetic"
        else _events_for_grid(updated_grid),
        "airports": _scene_airports(),
        "routes": routes,
        "weather_update": {
            **weather_change,
            "route_progress": route_progress,
            "resume_position": resume_position,
            "replanned": weather_change["drastic"],
            "weather_seed": weather_seed,
        },
    }


def _events_for_grid(grid):
    lat_values = sorted({point["lat"] for point in grid})
    lon_values = sorted({point["lon"] for point in grid})
    events = []
    for level in PRESSURE_LEVELS:
        for label in ("rain", "thunderstorm", "severe_storm"):
            events.extend(
                detect_events(
                    grid,
                    len(lat_values),
                    len(lon_values),
                    lat_values,
                    lon_values,
                    level,
                    label,
                )
            )
    return events