import numpy as np

from grid.romania_mask import ROMANIA_BOUNDS, inside_with_buffer

# Matches AIFS 0.25° resolution — going finer adds no real forecast detail.
DEFAULT_GRID_STEP_DEG = 0.25

# 5 vertical levels: added 500 hPa (~5.6 km) as a lower cruise layer, giving
# A* more altitude freedom (details.pdf allows extra vertical grids).
PRESSURE_LEVELS = [500, 400, 300, 250, 200]


def build_horizontal_grid(min_lat, max_lat, min_lon, max_lon, lat_step, lon_step,
                          mask=None):
    """
    Builds horizontal grid points over a rectangular envelope.

    mask: optional callable (lat, lon) -> bool. When provided, only points
    passing the filter are kept — used to shape the grid like Romania
    instead of filling the full bounding rectangle.
    """
    if lat_step <= 0 or lon_step <= 0:
        raise ValueError("lat_step and lon_step must be greater than 0")
    if max_lat <= min_lat or max_lon <= min_lon:
        raise ValueError("max_lat/max_lon must be greater than min_lat/min_lon")

    lats = np.arange(min_lat, max_lat + lat_step / 2, lat_step)
    lons = np.arange(min_lon, max_lon + lon_step / 2, lon_step)

    points = []
    for lat in lats:
        for lon in lons:
            lat_r = round(float(lat), 4)
            lon_r = round(float(lon), 4)
            if mask is not None and not mask(lat_r, lon_r):
                continue
            points.append({"lat": lat_r, "lon": lon_r})
    return points


def build_romania_grid(lat_step: float = DEFAULT_GRID_STEP_DEG,
                       lon_step: float = DEFAULT_GRID_STEP_DEG):
    """
    Full-country, Romania-shaped horizontal grid.

    Uses the details.pdf country envelope (43.5–48.5N, 19.5–30.0E) but keeps
    only points inside the border polygon (with a small buffer so coastal
    and frontier-adjacent cells survive). At 0.25° this yields ~900 points
    instead of the rectangle's ~2,048 — and it looks like Romania.
    """
    return build_horizontal_grid(
        ROMANIA_BOUNDS["min_lat"],
        ROMANIA_BOUNDS["max_lat"],
        ROMANIA_BOUNDS["min_lon"],
        ROMANIA_BOUNDS["max_lon"],
        lat_step,
        lon_step,
        mask=inside_with_buffer,
    )