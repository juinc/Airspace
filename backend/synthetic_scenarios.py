import random
from datetime import datetime, timezone

from grid.builder import build_horizontal_grid
from grid.coordinates import attach_scene_coordinates
from optimizer.astar import compute_route_metrics, find_avoided_high_exposure_cells, find_path, normalize_mode
from optimizer.stub_trajectory import generate_stub_route
from weather.client import PRESSURE_LEVELS
from weather.events import detect_events
from weather.normalize import weather_exposure_score

SCENARIO_SEEDS = {
    "random-storms": 4621,
    "heavy-storms": 91437,
    "clear-airspace": 187,
    "layered-random": 80631,
}
SCENARIO_TITLES = {
    "random-storms": "Random storms, rain, thunderstorms, and severe storms",
    "heavy-storms": "High-density synthetic storm field",
    "clear-airspace": "Clear airspace",
    "layered-random": "Independent random weather by altitude layer",
}


def build_synthetic_grid(scenario, config):
    """Create reproducible forecast-like data without making weather API calls."""
    if scenario not in SCENARIO_SEEDS:
        raise ValueError(f"Unknown scenario: {scenario}")

    points = build_horizontal_grid(
        config["min_lat"],
        config["max_lat"],
        config["min_lon"],
        config["max_lon"],
        config["lat_step"],
        config["lon_step"],
    )
    rng = random.Random(SCENARIO_SEEDS[scenario])
    layer_weather_cells = {}
    if scenario == "layered-random":
        weather_fractions = (0.72, 0.5, 0.28, 0.08)
        for level, weather_fraction in zip(PRESSURE_LEVELS, weather_fractions):
            shuffled_indices = list(range(len(points)))
            rng.shuffle(shuffled_indices)
            for index in shuffled_indices[: round(len(points) * weather_fraction)]:
                layer_weather_cells[(index, level)] = rng.choices(
                    ("rain", "thunderstorm", "severe_storm"),
                    weights=(0.2, 0.4, 0.4),
                    k=1,
                )[0]
        weather_cell_count = 0
    elif scenario == "random-storms":
        weather_cell_count = round(len(points) * 0.2)
    elif scenario == "heavy-storms":
        weather_cell_count = round(len(points) * 0.78)
    else:
        weather_cell_count = 0

    shuffled_indices = list(range(len(points)))
    rng.shuffle(shuffled_indices)
    weather_cells = {}
    for index in shuffled_indices[:weather_cell_count]:
        weather_cells[index] = rng.choices(
            ("rain", "thunderstorm", "severe_storm"),
            weights=(0.45, 0.30, 0.25),
            k=1,
        )[0]

    forecast_time = datetime.now(timezone.utc).isoformat()
    for index, point in enumerate(points):
        weather_type = weather_cells.get(index, "clear")
        cape, precipitation, vertical_velocity, wind_speed = _weather_values(
            weather_type, rng
        )
        humidity = rng.uniform(35, 75) if weather_type != "clear" else 0
        cloud_cover = rng.uniform(35, 100) if weather_type != "clear" else 0
        point.update(
            {
                "forecast_time": forecast_time,
                "cape": round(cape, 1),
                "precipitation": round(precipitation, 2),
                "cloud_cover": round(cloud_cover, 1),
                "levels": {},
            }
        )
        for level in PRESSURE_LEVELS:
            layer_weather_type = layer_weather_cells.get((index, level), weather_type)
            if scenario == "layered-random":
                layer_cape, layer_precipitation, layer_vertical_velocity, layer_wind_speed = (
                    _weather_values(layer_weather_type, rng)
                )
                layer_humidity = rng.uniform(35, 75) if layer_weather_type != "clear" else 0
                layer_cloud_cover = rng.uniform(35, 100) if layer_weather_type != "clear" else 0
            else:
                layer_cape = cape
                layer_precipitation = precipitation
                layer_vertical_velocity = vertical_velocity
                layer_wind_speed = wind_speed
                layer_humidity = humidity
                layer_cloud_cover = cloud_cover

            point["levels"][level] = {
                "temperature": None,
                "wind_speed": round(layer_wind_speed, 1),
                "wind_direction": None,
                "vertical_velocity": round(layer_vertical_velocity, 2),
                "geopotential_height": None,
                "relative_humidity": round(layer_humidity, 1),
                "cape": round(layer_cape, 1),
                "precipitation": round(layer_precipitation, 2),
                "cloud_cover": round(layer_cloud_cover, 1),
                "exposure_score": weather_exposure_score(
                    cape=layer_cape,
                    precipitation=layer_precipitation,
                    vertical_velocity=layer_vertical_velocity,
                    humidity=layer_humidity,
                    cloud_cover=layer_cloud_cover,
                ),
            }

    return attach_scene_coordinates(points, PRESSURE_LEVELS)


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


def build_synthetic_routes(grid, route, mode="Balanced"):
    canonical_mode = normalize_mode(mode)
    optimized = find_path(
        grid, route["origin"], route["destination"], mode=canonical_mode
    )
    baseline = generate_stub_route(
        route["origin"],
        route["destination"],
        grid,
        num_points=max(1, len(optimized) - 1),
    )
    return {
        "baseline": baseline,
        "optimized": optimized,
        "metrics": {
            "baseline": compute_route_metrics(baseline),
            "optimized": compute_route_metrics(optimized),
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
