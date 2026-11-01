import math

# Simplified Romania border polygon (lon, lat), ~0.2° accuracy — enough for
# masking a 0.25° grid. Swap in an official GeoJSON outline later; the
# algorithm stays identical.
ROMANIA_BORDER = [
    (22.35, 47.95), (22.95, 48.15), (23.30, 48.12), (23.90, 47.95),
    (24.10, 47.98), (24.55, 47.90), (24.90, 47.72), (25.30, 47.88),
    (25.90, 47.98), (26.25, 48.10), (26.62, 48.28), (26.95, 48.20),
    (27.35, 48.15), (27.90, 47.75), (28.25, 47.55), (28.75, 47.35),
    (28.95, 47.10), (29.10, 46.85), (29.15, 46.45), (29.30, 46.30),
    (29.55, 45.95), (29.60, 45.60), (29.65, 45.20), (29.55, 45.05),
    (29.05, 44.85), (28.75, 44.60), (28.55, 44.35), (28.30, 44.05),
    (28.05, 43.85), (27.95, 43.72), (27.60, 43.70), (27.20, 44.00),
    (26.60, 43.90), (25.97, 43.90), (25.45, 43.65), (24.90, 43.80),
    (24.00, 43.90), (23.40, 44.05), (22.95, 44.00), (22.45, 44.30),
    (22.35, 44.60), (22.10, 44.80), (21.55, 44.90), (21.40, 44.70),
    (20.75, 44.65), (20.60, 44.90), (20.26, 45.05), (20.45, 45.45),
    (20.35, 45.90), (20.20, 46.10), (20.45, 46.10), (20.25, 46.55),
    (20.65, 46.70), (21.40, 46.75), (21.65, 47.20), (22.10, 47.45),
]

# Full-country envelope (details.pdf recommended bounds).
ROMANIA_BOUNDS = {
    "min_lat": 43.5, "max_lat": 48.5,
    "min_lon": 19.5, "max_lon": 30.0,
}


def point_in_romania(lat: float, lon: float) -> bool:
    """Ray-casting point-in-polygon against the simplified border."""
    inside = False
    n = len(ROMANIA_BORDER)
    j = n - 1
    for i in range(n):
        lon_i, lat_i = ROMANIA_BORDER[i]
        lon_j, lat_j = ROMANIA_BORDER[j]
        if ((lat_i > lat) != (lat_j > lat)) and \
           lon < (lon_j - lon_i) * (lat - lat_i) / (lat_j - lat_i) + lon_i:
            inside = not inside
        j = i
    return inside


def inside_with_buffer(lat: float, lon: float, buffer_deg: float = 0.15) -> bool:
    """
    Point-in-polygon OR within buffer_deg of any border vertex. Keeps
    coastal/border-adjacent cells so airports near the frontier always
    have grid support.
    """
    if point_in_romania(lat, lon):
        return True
    for lon_v, lat_v in ROMANIA_BORDER:
        if math.hypot(lat - lat_v, lon - lon_v) <= buffer_deg:
            return True
    return False