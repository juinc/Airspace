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
    find_path,
    normalize_mode,
)
from optimizer.stub_trajectory import generate_baseline_route
from weather.client import PRESSURE_LEVELS
from weather.normalize import weather_exposure_score

# ---------------------------------------------------------------------------
# PERFORMANCE: 0.5° synthetic grid. Cuts A* nodes ~4x versus 0.25° — the
# single biggest backend win. Weather walls are lat/lon-anchored, so the
# scenarios read identically; clouds are large enough that the coarser
# sampling is invisible.
# ---------------------------------------------------------------------------
SYNTHETIC_CONFIG = {
    "min_lat": 43.5,
    "max_lat": 48.5,
    "min_lon": 19.5,
    "max_lon": 30.0,
    "lat_step": 0.5,
    "lon_step": 0.5,
}

# ---------------------------------------------------------------------------
# Airport registry — every scenario (legacy and multi-flight) draws from here.
# ---------------------------------------------------------------------------
AIRPORTS = {
    "LCCR": {"name": "LCCR", "city": "Craiova", "lat": 44.3180, "lon": 23.8886},
    "LRCL": {"name": "LRCL", "city": "Cluj-Napoca", "lat": 46.7834, "lon": 23.6842},
    "LRBS": {"name": "LRBS", "city": "Bucharest", "lat": 44.5711, "lon": 26.0850},
    "LRTM": {"name": "LRTM", "city": "Timisoara", "lat": 45.8097, "lon": 21.3375},
    "LRIA": {"name": "LRIA", "city": "Iasi", "lat": 47.1786, "lon": 27.6208},
    "LRC": {"name": "LRC", "city": "Constanta", "lat": 44.3622, "lon": 28.4872},
}

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

# ---------------------------------------------------------------------------
# Multi-flight scenarios — several aircraft, several airports, one weather field.
# ---------------------------------------------------------------------------
MULTI_FLIGHT_SCENARIOS = {
    "crossroads-storm": {
        "title": "Storm crossroads — three corridors, three walls",
        "flights": [("LCCR", "LRCL"), ("LRTM", "LRBS"), ("LRC", "LRIA")],
    },
    "converge-bucharest": {
        "title": "Convergence on Bucharest — four arrivals, one storm ring",
        "flights": [("LCCR", "LRBS"), ("LRCL", "LRBS"), ("LRTM", "LRBS"), ("LRIA", "LRBS")],
    },
    "carpathian-siege": {
        "title": "Carpathian siege — triangle flights around a storm mass",
        "flights": [("LRCL", "LRBS"), ("LRBS", "LRTM"), ("LRTM", "LRCL")],
    },
}

MULTI_SEEDS = {
    "crossroads-storm": 2101,
    "converge-bucharest": 2202,
    "carpathian-siege": 2303,
}

# Legacy single-corridor anchor (Craiova -> Cluj).
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


def _corridor_frame(origin, destination, lat: float, lon: float):
    """(progress, lateral) relative to an arbitrary airport-to-airport line."""
    cos_mid = math.cos(math.radians((origin["lat"] + destination["lat"]) / 2))
    ex = (lon - origin["lon"]) * cos_mid
    ey = lat - origin["lat"]
    vx = (destination["lon"] - origin["lon"]) * cos_mid
    vy = destination["lat"] - origin["lat"]
    len_sq = vx * vx + vy * vy
    if len_sq <= 1e-12:
        return 0.0, 0.0
    progress = (ex * vx + ey * vy) / len_sq
    lateral = (ex * vy - ey * vx) / math.sqrt(len_sq) / _LATERAL_NORMALIZATION_DEG
    return progress, lateral


def _corridors_for(scenario):
    return [
        (AIRPORTS[origin], AIRPORTS[dest])
        for origin, dest in MULTI_FLIGHT_SCENARIOS[scenario]["flights"]
    ]


def _multi_cell_plan(scenario, lat: float, lon: float):
    """Weather plan for the multi-flight scenarios, anchored to their corridors."""
    corridors = _corridors_for(scenario)

    if scenario == "crossroads-storm":
        for i, (origin, dest) in enumerate(corridors):
            progress, lateral = _corridor_frame(origin, dest, lat, lon)
            if not (0.05 <= progress <= 0.95) or abs(lateral) > 1.6:
                continue
            if 0.42 <= progress <= 0.58:
                gap_side = 1.0 if i % 2 == 0 else -1.0
                if not (0.15 <= gap_side * lateral <= 0.55):
                    return "severe_storm", None
            elif abs(lateral) <= 0.8 and 0.25 <= progress <= 0.75:
                return "thunderstorm", None
        return "clear", None

    if scenario == "converge-bucharest":
        hub = AIRPORTS["LRBS"]
        cos = math.cos(math.radians(hub["lat"]))
        dx = (lon - hub["lon"]) * cos
        dy = lat - hub["lat"]
        dist = math.hypot(dx, dy)
        if dist <= 0.12:
            return "rain", None
        if 0.28 <= dist <= 0.62:
            bearing = math.degrees(math.atan2(dx, dy)) % 360.0
            in_gap = (250.0 <= bearing <= 335.0) or (5.0 <= bearing <= 55.0)
            if not in_gap:
                return "severe_storm", None
        return "clear", None

    if scenario == "carpathian-siege":
        center_lat, center_lon = 45.65, 25.10
        cos = math.cos(math.radians(center_lat))
        dist = math.hypot((lon - center_lon) * cos, lat - center_lat)
        if dist <= 0.85:
            return "severe_storm", None
        for origin, dest in corridors:
            progress, lateral = _corridor_frame(origin, dest, lat, lon)
            if 0.10 <= progress <= 0.90 and abs(lateral) <= 0.7:
                return "thunderstorm", None
        return "clear", None

    return "clear", None


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
    is_multi = scenario in MULTI_FLIGHT_SCENARIOS
    if is_multi:
        seed = MULTI_SEEDS[scenario] + weather_seed
    elif scenario in SCENARIO_SEEDS:
        seed = SCENARIO_SEEDS[scenario] + weather_seed
    else:
        raise ValueError(f"Unknown scenario: {scenario}")

    points = build_horizontal_grid(
        config["min_lat"], config["max_lat"],
        config["min_lon"], config["max_lon"],
        config["lat_step"], config["lon_step"],
        mask=inside_with_buffer,
    )
    rng = random.Random(seed)
    forecast_time = datetime.now(timezone.utc).isoformat()

    for point in points:
        point["forecast_time"] = forecast_time
        point["levels"] = {}
        if is_multi:
            surface_type, layer_overrides = _multi_cell_plan(
                scenario, point["lat"], point["lon"]
            )
        else:
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
    # 0.8° radius: covers enough cells on the 0.5° grid to reliably
    # trigger the "drastic" replan threshold.
    radius_deg = 0.8

    for point in grid:
        if (abs(point["lat"] - target["lat"]) <= radius_deg
                and abs(point["lon"] - target["lon"]) <= radius_deg):
            _apply_point_weather(point, "severe_storm", rng)

    return grid


def build_quick_events(grid):
    """
    PERFORMANCE: the frontend only displays the event COUNT (status line).
    Full scipy cluster detection (15 passes over the grid) is pure waste
    here — this counts storm cells directly in one pass.
    """
    severe = thunder = rain = 0
    for point in grid:
        cape = point.get("cape") or 0
        precipitation = point.get("precipitation") or 0
        if cape >= 2500:
            severe += 1
        elif cape >= 1000:
            thunder += 1
        elif precipitation >= 1:
            rain += 1

    events = []
    if severe:
        events.append({"type": "severe_storm", "cell_count": severe})
    if thunder:
        events.append({"type": "thunderstorm", "cell_count": thunder})
    if rain:
        events.append({"type": "rain", "cell_count": rain})
    return events


def build_synthetic_events(grid, pressure_levels=PRESSURE_LEVELS):
    """Full scipy-based event detection — kept for API compatibility."""
    from weather.events import detect_events

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
            # PERFORMANCE: the frontend never renders avoided cells, and
            # computing them rebuilds the entire node graph per flight.
            "avoided_high_exposure_cells": [],
        },
    }


def build_multi_flight_routes(grid, flight_pairs, mode="Balanced", profile=None):
    """One route pair per (origin_code, destination_code) — shared weather grid."""
    flights = []
    for index, (origin_code, destination_code) in enumerate(flight_pairs):
        origin = AIRPORTS[origin_code]
        destination = AIRPORTS[destination_code]
        flight = build_synthetic_routes(
            grid, {"origin": origin, "destination": destination}, mode, profile
        )
        flight["id"] = f"F{index + 1}"
        flight["origin"] = origin_code
        flight["destination"] = destination_code
        flights.append(flight)
    return flights


def _weather_values(weather_type, rng):
    if weather_type == "rain":
        return 0, rng.uniform(1, 8), 0, rng.uniform(15, 80)
    if weather_type == "thunderstorm":
        return rng.uniform(1000, 2499), rng.uniform(1, 8), rng.uniform(1.5, 3), rng.uniform(15, 99)
    if weather_type == "severe_storm":
        return rng.uniform(2500, 3500), rng.uniform(4, 15), rng.uniform(1.5, 3), rng.uniform(100, 180)
    return 0, 0, 0, 15