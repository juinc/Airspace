import copy
import math
import random
from datetime import datetime, timezone

from grid.builder import build_horizontal_grid
from grid.romania_mask import inside_with_buffer
from grid.coordinates import attach_scene_coordinates
from optimizer.astar import (
    AircraftProfile,
    compute_route_metrics,
    estimate_route_position,
    extend_with_flight_phases,
    find_avoided_high_exposure_cells,
    find_path,
    normalize_mode,
)
from optimizer.stub_trajectory import generate_baseline_route
from weather.client import PRESSURE_LEVELS
from weather.events import detect_events
from weather.normalize import weather_exposure_score

SCENARIO_TITLES = {
    "storm-wall": "Full-altitude storm wall with a single lateral gap",
    "over-the-top": "Low-level storms across the corridor — climb over the top",
    "low-corridor": "High-level storms across the corridor — descend underneath",
    "slalom": "Alternating storm columns — forced lateral slalom",
    "fuel-critical": "Storm wall with a far-edge gap — maximum-detour fuel test",
    "in-flight-replan": "Clear skies, then a storm spawns on the route ahead",
    "clear-airspace": "Clear airspace",
}

SCENARIO_SEEDS = {
    "storm-wall": 1101,
    "over-the-top": 1202,
    "low-corridor": 1303,
    "slalom": 1404,
    "fuel-critical": 1505,
    "in-flight-replan": 1606,
    "clear-airspace": 187,
}

# Scenarios are anchored to the Craiova->Cluj flight line, not grid bounds.
ROUTE_ORIGIN_LAT = 44.3180
ROUTE_ORIGIN_LON = 23.8886
ROUTE_DEST_LAT = 46.783389
ROUTE_DEST_LON = 23.684194

_LATERAL_NORMALIZATION_DEG = 2.5
_COS_MID_LAT = math.cos(math.radians((ROUTE_ORIGIN_LAT + ROUTE_DEST_LAT) / 2))

_ROUTE_VEC_EX = (ROUTE_DEST_LON - ROUTE_ORIGIN_LON) * _COS_MID_LAT
_ROUTE_VEC_EY = ROUTE_DEST_LAT - ROUTE_ORIGIN_LAT
_ROUTE_LEN_SQ = _ROUTE_VEC_EX ** 2 + _ROUTE_VEC_EY ** 2
_ROUTE_LEN = math.sqrt(_ROUTE_LEN_SQ)


def _route_frame(lat: float, lon: float):
    """(progress, lateral) of a point relative to the Craiova->Cluj line."""
    ex = (lon - ROUTE_ORIGIN_LON) * _COS_MID_LAT
    ey = lat - ROUTE_ORIGIN_LAT
    progress = (ex * _ROUTE_VEC_EX + ey * _ROUTE_VEC_EY) / _ROUTE_LEN_SQ
    lateral = (ex * _ROUTE_VEC_EY - ey * _ROUTE_VEC_EX) / _ROUTE_LEN / _LATERAL_NORMALIZATION_DEG
    return progress, lateral


def _cell_plan(scenario, progress, lateral):
    if scenario == "storm-wall":
        if 0.42 <= progress <= 0.58 and not (0.30 <= lateral <= 0.55):
            return "severe_storm", None
    elif scenario == "over-the-top":
        if 0.35 <= progress <= 0.70:
            return "severe_storm", {
                500: "severe_storm", 400: "severe_storm", 300: "severe_storm",
                250: "clear", 200: "clear",
            }
    elif scenario == "low-corridor":
        if 0.35 <= progress <= 0.70:
            return "severe_storm", {
                500: "clear", 400: "clear", 300: "clear",
                250: "severe_storm", 200: "severe_storm",
            }
    elif scenario == "slalom":
        columns = (
            (0.15, 0.25, lambda l: l < 0.0),
            (0.35, 0.45, lambda l: l >= 0.0),
            (0.55, 0.65, lambda l: l < 0.0),
            (0.75, 0.85, lambda l: l >= 0.0),
        )
        for lo, hi, side in columns:
            if lo <= progress <= hi and side(lateral):
                return "thunderstorm", None
    elif scenario == "fuel-critical":
        if 0.50 <= progress <= 0.65 and lateral > -0.60:
            return "severe_storm", None
    return "clear", None


def _apply_point_weather(point, surface_type, rng, layer_overrides=None):
    cape, precipitation, _, wind_speed = _weather_values(surface_type, rng)
    humidity = rng.uniform(35, 75) if surface_type != "clear" else 0
    cloud_cover = rng.uniform(35, 100) if surface_type != "clear" else 0
    point["cape"] = round(cape, 1)
    point["precipitation"] = round(precipitation, 2)
    point["cloud_cover"] = round(cloud_cover, 1)

    for level in PRESSURE_LEVELS:
        layer_type = (layer_overrides or {}).get(level, surface_type)
        l_cape, l_precip, l_vv, l_wind = _weather_values(layer_type, rng)
        l_humidity = rng.uniform(35, 75) if layer_type != "clear" else 0
        l_cloud = rng.uniform(35, 100) if layer_type != "clear" else 0
        point["levels"][level] = {
            "temperature": None,
            "wind_speed": round(l_wind, 1),
            "wind_direction": None,
            "vertical_velocity": round(l_vv, 2),
            "geopotential_height": None,
            "relative_humidity": round(l_humidity, 1),
            "exposure_score": weather_exposure_score(
                cape=l_cape,
                precipitation=l_precip,
                vertical_velocity=l_vv,
                humidity=l_humidity,
                cloud_cover=l_cloud,
            ),
        }


def build_synthetic_grid(scenario, config, weather_seed=0):
    if scenario not in SCENARIO_SEEDS:
        raise ValueError(f"Unknown scenario: {scenario}")

    points = build_horizontal_grid(
        config["min_lat"], config["max_lat"],
        config["min_lon"], config["max_lon"],
        config["lat_step"], config["lon_step"],
        mask=inside_with_buffer,
    )
    rng = random.Random(SCENARIO_SEEDS[scenario] + weather_seed)
    forecast_time = datetime.now(timezone.utc).isoformat()

    for point in points:
        point["forecast_time"] = forecast_time
        point["levels"] = {}
        progress, lateral = _route_frame(point["lat"], point["lon"])
        surface_type, layer_overrides = _cell_plan(scenario, progress, lateral)
        _apply_point_weather(point, surface_type, rng, layer_overrides)

    return attach_scene_coordinates(points, PRESSURE_LEVELS)


def spawn_route_blockage(previous_grid, previous_route, route_progress, weather_seed=0):
    if not previous_grid:
        raise ValueError("previous_grid must not be empty")
    if not previous_route or len(previous_route) < 2:
        raise ValueError("previous_route needs at least two waypoints")

    rng = random.Random(70000 + weather_seed)
    grid = copy.deepcopy(previous_grid)

    if route_progress >= 0.75:
        return grid

    target_progress = min(0.97, route_progress + 0.25 + rng.uniform(0, 0.10))
    target = estimate_route_position(previous_route, target_progress)
    radius_deg = 0.45

    for point in grid:
        if (abs(point["lat"] - target["lat"]) <= radius_deg
                and abs(point["lon"] - target["lon"]) <= radius_deg):
            _apply_point_weather(point, "severe_storm", rng)

    return grid


def build_synthetic_events(grid, pressure_levels=PRESSURE_LEVELS):
    if not grid:
        return []
    lat_values = sorted({point["lat"] for point in grid})
    lon_values = sorted({point["lon"] for point in grid})
    events = []
    for level in pressure_levels:
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


def build_synthetic_routes(grid, route, mode="Balanced", profile=None):
    canonical_mode = normalize_mode(mode)
    profile = profile or AircraftProfile()
    optimized = find_path(
        grid, route["origin"], route["destination"], mode=canonical_mode, profile=profile
    )
    optimized = extend_with_flight_phases(
        optimized, route["origin"], route["destination"], profile, grid
    )
    baseline = generate_baseline_route(
        route["origin"],
        route["destination"],
        grid,
        num_points=max(1, len(optimized) - 1),
        profile=profile,
    )
    baseline = extend_with_flight_phases(
        baseline, route["origin"], route["destination"], profile, grid
    )
    return {
        "baseline": baseline,
        "optimized": optimized,
        "metrics": {
            "baseline": compute_route_metrics(baseline, profile),
            "optimized": compute_route_metrics(optimized, profile),
        },
        "reasoning": {
            "mode": canonical_mode,
            "avoided_high_exposure_cells": find_avoided_high_exposure_cells(
                grid, baseline, optimized
            ),
        },
    }


def _weather_values(weather_type, rng):
    if weather_type == "rain":
        return 0, rng.uniform(1, 8), 0, rng.uniform(15, 80)
    if weather_type == "thunderstorm":
        return rng.uniform(1000, 2499), rng.uniform(1, 8), rng.uniform(1.5, 3), rng.uniform(15, 99)
    if weather_type == "severe_storm":
        return rng.uniform(2500, 3500), rng.uniform(4, 15), rng.uniform(1.5, 3), rng.uniform(100, 180)
    return 0, 0, 0, 15