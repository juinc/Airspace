import numpy as np

from grid.romania_mask import ROMANIA_BOUNDS, inside_with_buffer

# Matches AIFS 0.25° resolution — do not go finer, it adds no real detail.
GRID_STEP_DEG = 0.25

# 5 vertical levels: added 500 hPa (~5.6 km) as a lower cruise layer,
# giving A* more altitude freedom (details.pdf allows extra vertical grids).
PRESSURE_LEVELS = [500, 400, 300, 250, 200]

# Open-Meteo accepts multiple coordinate pairs per request; chunk to stay
# well within URL/response limits.
CHUNK_SIZE = 100


def build_romania_grid(fetch_weather_chunk):
    """
    Builds the full-country, Romania-shaped grid points.

    fetch_weather_chunk(coords, pressure_levels) -> list of level-data dicts
        ^ CONNECT THIS to your existing Open-Meteo fetch. It receives a list
        of (lat, lon) tuples (<= CHUNK_SIZE) and must return one entry per
        coordinate in the same order, each shaped like your current per-point
        "levels" payload: {level: {temperature: ..., wind_speed: ..., ...}}.

    Returns grid_points in the exact shape your pipeline expects downstream
    (list of {"lat", "lon", "levels"} dicts), ready for
    attach_scene_coordinates().
    """
    lats = np.arange(
        ROMANIA_BOUNDS["min_lat"],
        ROMANIA_BOUNDS["max_lat"] + GRID_STEP_DEG,
        GRID_STEP_DEG,
    )
    lons = np.arange(
        ROMANIA_BOUNDS["min_lon"],
        ROMANIA_BOUNDS["max_lon"] + GRID_STEP_DEG,
        GRID_STEP_DEG,
    )

    candidates = [
        (round(lat, 3), round(lon, 3))
        for lat in lats for lon in lons
        if inside_with_buffer(round(lat, 3), round(lon, 3))
    ]
    # ~900 horizontal points, shaped like Romania (vs 2,048 in the rectangle).

    grid_points = []
    for chunk_start in range(0, len(candidates), CHUNK_SIZE):
        chunk = candidates[chunk_start:chunk_start + CHUNK_SIZE]
        weather = fetch_weather_chunk(chunk, PRESSURE_LEVELS)

        for (lat, lon), levels in zip(chunk, weather):
            grid_points.append({
                "lat": lat,
                "lon": lon,
                "levels": levels,
            })

    return grid_points