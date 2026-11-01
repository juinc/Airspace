from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from pydantic import BaseModel, Field
from requests import RequestException

from weather.client import (
    FORECAST_DAYS,
    FORECAST_STEP_HOURS,
    OPEN_METEO_MODEL,
    PRESSURE_LEVELS as _CLIENT_PRESSURE_LEVELS,
    build_variable_list,
    fetch_forecast,
    parse_response,
    select_forecast_index,
)
from weather.cache import build_cache_key, load_cache, save_cache
from weather.events import detect_events
from grid.builder import build_horizontal_grid
from grid.romania_mask import inside_with_buffer, ROMANIA_BORDER
from grid.coordinates import (
    attach_scene_coordinates,
    latlon_to_scene_xz,
    GRID_ORIGIN_LAT,
    GRID_ORIGIN_LON,
    VERTICAL_EXAGGERATION,
)
from optimizer.astar import (
    AircraftProfile,
    BASELINE_PRESSURE_LEVEL,
    ROUTE_INTERSECTION_CLEARANCE_KM,
    WEATHER_WEIGHTS,
    compute_route_metrics,
    assess_route_weather_change,
    estimate_route_position,
    find_path,
    normalize_mode,
)
from optimizer.stub_trajectory import (
    generate_baseline_route,
    match_route_waypoint_count,
)
from synthetic_scenarios import (
    AIRPORTS,
    MULTI_FLIGHT_SCENARIOS,
    SCENARIO_TITLES,
    SYNTHETIC_CONFIG,
    build_multi_flight_routes,
    build_quick_events,
    build_synthetic_grid,
    build_synthetic_routes,
    spawn_route_blockage,
)

PRESSURE_LEVELS = sorted(set(_CLIENT_PRESSURE_LEVELS) | {500})

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
app.add_middleware(GZipMiddleware, minimum_size=500)

# PERFORMANCE: 0.5° default grid. Halves live-fetch points (~4x fewer A*
# nodes) with no visible loss — AIFS itself is 0.25° and clouds are huge.
DEFAULT_CONFIG = {
    "min_lat": 43.5,
    "max_lat": 48.5,
    "min_lon": 19.5,
    "max_lon": 30.0,
    "lat_step": 0.5,
    "lon_step": 0.5,
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

# PERFORMANCE: fewer, larger Open-Meteo requests (POST JSON body — no URL
# limit). ~200 grid points now fit in a single fetch.
_FETCH_CHUNK_SIZE = 250

SCENE_CACHE_VERSION = "full-aifs-scene-v3"

# ---------------------------------------------------------------------------
# In-memory scenario cache. Synthetic scenarios are deterministic given
# (scenario, mode, seed, progress, aircraft) — recomputing A* for a repeat
# visit is pure waste. Bounded, oldest-entry eviction.
# ---------------------------------------------------------------------------
_SCENARIO_CACHE = {}
_SCENARIO_CACHE_MAX = 16


def _cached_scenario(key, builder):
    cached = _SCENARIO_CACHE.get(key)
    if cached is not None:
        return cached
    payload = builder()
    if len(_SCENARIO_CACHE) >= _SCENARIO_CACHE_MAX:
        _SCENARIO_CACHE.pop(next(iter(_SCENARIO_CACHE)))
    _SCENARIO_CACHE[key] = payload
    return payload


class AircraftProfileRequest(BaseModel):
    """CJ3 nominal defaults; caller overrides remain simulation-only."""
    cruise_speed_kmh: float = Field(default=AircraftProfile().cruise_speed_kmh, ge=300, le=1000)
    climb_rate_m_per_min: float = Field(default=AircraftProfile().climb_rate_m_per_min, ge=60, le=1500)
    descent_rate_m_per_min: float = Field(default=AircraftProfile().descent_rate_m_per_min, ge=60, le=1500)
    altitude_change_penalty_min: float = Field(default=AircraftProfile().altitude_change_penalty_min, ge=0, le=30)
    weight_kg: float = Field(default=AircraftProfile().weight_kg, ge=5000, le=500000)
    fuel_burn_kg_per_hour: float = Field(default=AircraftProfile().fuel_burn_kg_per_hour, ge=100, le=20000)
    fuel_capacity_kg: float = Field(default=AircraftProfile().fuel_capacity_kg, ge=1000, le=200000)
    max_altitude_km: float = Field(default=AircraftProfile().max_altitude_km, ge=5, le=20)


def _aircraft_profile(req) -> AircraftProfile:
    return AircraftProfile(**req.aircraft.model_dump())


class GridRequest(BaseModel):
    min_lat: Optional[float] = None
    max_lat: Optional[float] = None
    min_lon: Optional[float] = None
    max_lon: Optional[float] = None
    lat_step: Optional[float] = None
    lon_step: Optional[float] = None
    test_mode: bool = True
    mode: str = "Balanced"
    aircraft: AircraftProfileRequest = Field(default_factory=AircraftProfileRequest)


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
    aircraft: AircraftProfileRequest = Field(default_factory=AircraftProfileRequest)


_NON_GRID_FIELDS = {"test_mode", "mode", "aircraft"}


def _grid_overrides(req):
    return {
        key: value
        for key, value in req.model_dump().items()
        if value is not None and key not in _NON_GRID_FIELDS
    }


def _airport_scene_entry(code: str) -> dict:
    airport = AIRPORTS[code]
    x, z = latlon_to_scene_xz(airport["lat"], airport["lon"])
    return {
        "name": f"{airport['name']} {airport['city']}",
        "lat": airport["lat"],
        "lon": airport["lon"],
        "x": x,
        "y": 0.0,
        "z": z,
    }


def _airports_for_flight_pairs(pairs) -> list:
    codes = []
    for origin, destination in pairs:
        for code in (origin, destination):
            if code not in codes:
                codes.append(code)
    return [_airport_scene_entry(code) for code in codes]


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


def _scene_romania_border():
    border = []
    for lon, lat in ROMANIA_BORDER:
        x, z = latlon_to_scene_xz(lat, lon)
        border.append({"x": round(x, 3), "z": round(z, 3)})
    return border


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


def _fetch_weather_chunk(points, force_refresh=False):
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


def _fetch_weather(points, force_refresh=False):
    all_results = []
    sources = set()
    for start in range(0, len(points), _FETCH_CHUNK_SIZE):
        chunk = points[start:start + _FETCH_CHUNK_SIZE]
        results, source = _fetch_weather_chunk(chunk, force_refresh=force_refresh)
        all_results.extend(results)
        sources.add(source)
    source = "live" if "live" in sources else "cache"
    return all_results, source


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


def _routing_assumptions(profile: AircraftProfile):
    return {
        "aircraft_profile": profile.as_dict(),
        "enroute_route_clearance_km": ROUTE_INTERSECTION_CLEARANCE_KM,
        "route_intersection_policy": "3D centerline; takeoff and landing segments excluded",
        "operational_collision_avoidance": False,
        "baseline_pressure_level_hpa": BASELINE_PRESSURE_LEVEL,
        "climb_descent_model": "parallel_climb_max_time",
        "phase_geometry": "full_route_continuous_vertical_profile",
        "weight_model": "climb_rate_scaled_by_reference_weight_ratio",
        "fuel_model": "linear_burn_rate_times_modeled_time",
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
    results = attach_scene_coordinates(results, PRESSURE_LEVELS)
    return {
        "source": source,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        **_forecast_metadata(results),
        "data": results,
    }


def _scene_grid(req, force_refresh=False):
    cfg = {**DEFAULT_CONFIG, **_grid_overrides(req)}
    try:
        points = build_horizontal_grid(
            cfg["min_lat"],
            cfg["max_lat"],
            cfg["min_lon"],
            cfg["max_lon"],
            cfg["lat_step"],
            cfg["lon_step"],
            mask=inside_with_buffer,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))

    if req.test_mode:
        points = points[:36]

    grid_results, source = _fetch_weather(points, force_refresh=force_refresh)
    return cfg, attach_scene_coordinates(grid_results, PRESSURE_LEVELS), source


def _scene_routes(grid_results, mode, profile: AircraftProfile):
    optimized_route = find_path(
        grid_results, ROUTE["origin"], ROUTE["destination"], mode=mode, profile=profile
    )
    baseline_route = generate_baseline_route(
        ROUTE["origin"],
        ROUTE["destination"],
        grid_results,
        num_points=1,
        profile=profile,
    )
    baseline_route = match_route_waypoint_count(baseline_route, len(optimized_route))
    canonical_mode = normalize_mode(mode)
    return {
        "baseline": baseline_route,
        "optimized": optimized_route,
        "metrics": {
            "baseline": compute_route_metrics(baseline_route, profile),
            "optimized": compute_route_metrics(optimized_route, profile),
        },
        "reasoning": {
            "mode": canonical_mode,
            # PERFORMANCE: frontend never renders these; computing them
            # rebuilds the full node graph. Dropped.
            "avoided_high_exposure_cells": [],
        },
    }


@app.post("/weather-grid")
def weather_grid(req: GridRequest):
    cfg, results, source = _scene_grid(req)
    return {
        "source": source,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "point_count": len(results),
        **_forecast_metadata(results),
        "scene_config": {
            "origin_lat": GRID_ORIGIN_LAT,
            "origin_lon": GRID_ORIGIN_LON,
            "scene_unit": "km",
            "vertical_exaggeration": VERTICAL_EXAGGERATION,
        },
        "grid_config": cfg,
        "data": results,
    }


@app.post("/weather-events")
def weather_events(req: GridRequest):
    cfg = {**DEFAULT_CONFIG, **_grid_overrides(req)}

    if req.test_mode:
        points = [
            {"lat": airport["lat"], "lon": airport["lon"]}
            for airport in ROUTE.values()
        ]
    else:
        try:
            points = build_horizontal_grid(
                cfg["min_lat"], cfg["max_lat"], cfg["min_lon"], cfg["max_lon"],
                cfg["lat_step"], cfg["lon_step"],
                mask=inside_with_buffer,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error))

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
    try:
        mode = normalize_mode(req.mode)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))

    profile = _aircraft_profile(req)
    cfg, grid_results, weather_source = _scene_grid(req)
    forecast_valid_times = sorted(
        {
            point["forecast_time"]
            for point in grid_results
            if point.get("forecast_time") is not None
        }
    )
    cache_key = build_cache_key(
        SCENE_CACHE_VERSION,
        config=cfg,
        mode=mode,
        aircraft=req.aircraft.model_dump(),
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
        cached_meta.setdefault("romania_border", _scene_romania_border())
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
        routes = _scene_routes(grid_results, mode, profile)
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
            "romania_border": _scene_romania_border(),
            "grid_config": cfg,
            "routing_assumptions": _routing_assumptions(profile),
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
    try:
        mode = normalize_mode(req.mode)
        profile = _aircraft_profile(req)
        _, grid_results, _ = _scene_grid(req)
        return _scene_routes(grid_results, mode, profile)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))


@app.post("/replan")
def replan(req: ReplanRequest):
    try:
        mode = normalize_mode(req.mode)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    profile = _aircraft_profile(req)

    if req.previous_source == "synthetic":
        updated_grid = spawn_route_blockage(
            req.previous_grid,
            req.previous_route,
            req.route_progress,
            req.weather_seed,
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
        "in-flight-replan",
        req.weather_seed,
        profile,
    )


@app.get("/test-scenarios/{scenario}")
def test_scenario(
    scenario: str,
    mode: str = "Balanced",
    route_progress: float = 0.35,
    weather_seed: int = 0,
    aircraft: Optional[AircraftProfileRequest] = None,
):
    profile = AircraftProfile(**aircraft.model_dump()) if aircraft else AircraftProfile()
    aircraft_key = tuple(sorted(aircraft.model_dump().items())) if aircraft else None
    cache_key = (scenario, mode, round(route_progress, 3), weather_seed, aircraft_key)

    # --- Multi-flight scenarios: several aircraft across several airports ---
    if scenario in MULTI_FLIGHT_SCENARIOS:
        spec = MULTI_FLIGHT_SCENARIOS[scenario]

        def build_multi():
            try:
                grid = build_synthetic_grid(scenario, SYNTHETIC_CONFIG, weather_seed)
                flights = build_multi_flight_routes(grid, spec["flights"], mode, profile)
            except ValueError as error:
                raise HTTPException(status_code=400, detail=str(error)) from error
            return {
                "meta": {
                    "source": "synthetic",
                    "scenario": scenario,
                    "scenario_title": spec["title"],
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "origin_lat": GRID_ORIGIN_LAT,
                    "origin_lon": GRID_ORIGIN_LON,
                    "scene_unit": "km",
                    "vertical_exaggeration": VERTICAL_EXAGGERATION,
                    "map_bounds": _scene_map_bounds(),
                    "romania_border": _scene_romania_border(),
                    "grid_config": SYNTHETIC_CONFIG,
                    "routing_assumptions": _routing_assumptions(profile),
                    "trajectory_status": f"A* multi-flight scenario ({len(flights)} aircraft)",
                },
                "grid": grid,
                "events": build_quick_events(grid),
                "airports": _airports_for_flight_pairs(spec["flights"]),
                "flights": flights,
                # Legacy compat: single-flight consumers (HUD, metrics panel)
                # read payload.routes — expose the first flight under that key.
                "routes": flights[0],
            }

        return _cached_scenario(cache_key, build_multi)

    if scenario == "real-meteo":
        grid_request = GridRequest(test_mode=False, mode=mode)
        if aircraft:
            grid_request.aircraft = aircraft
        payload = test_scene_data(grid_request)
        meta = payload.setdefault("meta", {})
        meta["scenario"] = scenario
        meta["scenario_title"] = "Open-Meteo forecast"
        return payload

    if scenario == "in-flight-replan":
        if not 0 <= route_progress <= 1:
            raise HTTPException(status_code=400, detail="route_progress must be between 0 and 1")

        def build_replan():
            try:
                previous_grid = build_synthetic_grid("clear-airspace", SYNTHETIC_CONFIG)
                previous_routes = build_synthetic_routes(previous_grid, ROUTE, mode, profile)
                updated_grid = spawn_route_blockage(
                    previous_grid,
                    previous_routes["optimized"],
                    route_progress,
                    weather_seed,
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
                profile,
            )

        return _cached_scenario(cache_key, build_replan)

    if scenario not in SCENARIO_TITLES or scenario == "clear-airspace":
        raise HTTPException(status_code=404, detail=f"Unknown scenario: {scenario}")

    def build_legacy():
        try:
            grid = build_synthetic_grid(scenario, SYNTHETIC_CONFIG, weather_seed)
            routes = build_synthetic_routes(grid, ROUTE, mode, profile)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error))
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
                "romania_border": _scene_romania_border(),
                "grid_config": SYNTHETIC_CONFIG,
                "routing_assumptions": _routing_assumptions(profile),
                "trajectory_status": f"Synthetic A* route ({routes['reasoning']['mode']})",
            },
            "grid": grid,
            "events": build_quick_events(grid),
            "airports": _scene_airports(),
            "routes": routes,
        }

    return _cached_scenario(cache_key, build_legacy)


def _weather_replan_payload(
    previous_grid,
    previous_route,
    route_progress,
    mode,
    updated_grid,
    source,
    scenario,
    weather_seed=0,
    profile=None,
):
    profile = profile or AircraftProfile()
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
            profile=profile,
        )
        trajectory_status = f"A* replanned from {route_progress:.0%} route progress"
    else:
        optimized_route = previous_route
        trajectory_status = "Weather change below drastic threshold; keeping current route"

    baseline_route = generate_baseline_route(
        ROUTE["origin"],
        ROUTE["destination"],
        updated_grid,
        num_points=1,
        profile=profile,
    )
    baseline_route = match_route_waypoint_count(baseline_route, len(optimized_route))
    routes = {
        "baseline": baseline_route,
        "previous_optimized": previous_route,
        "optimized": optimized_route,
        "metrics": {
            "baseline": compute_route_metrics(baseline_route, profile),
            "optimized": compute_route_metrics(optimized_route, profile),
        },
        "reasoning": {
            "mode": canonical_mode,
            "weather_change": weather_change,
            "avoided_high_exposure_cells": [],
        },
    }
    valid_times = _forecast_metadata(updated_grid)
    return {
        "meta": {
            "source": source,
            "scenario": scenario,
            "scenario_title": SCENARIO_TITLES.get(scenario, "In-flight replan"),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            **valid_times,
            "origin_lat": GRID_ORIGIN_LAT,
            "origin_lon": GRID_ORIGIN_LON,
            "scene_unit": "km",
            "vertical_exaggeration": VERTICAL_EXAGGERATION,
            "map_bounds": _scene_map_bounds(),
            "romania_border": _scene_romania_border(),
            "grid_config": DEFAULT_CONFIG,
            "routing_assumptions": _routing_assumptions(profile),
            "trajectory_status": trajectory_status,
        },
        "grid": updated_grid,
        "events": build_quick_events(updated_grid)
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