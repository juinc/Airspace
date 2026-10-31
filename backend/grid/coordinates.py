import math

# Locked shared constants — frontend must use the identical origin
# if it ever needs to reason about positions independently.
GRID_ORIGIN_LAT = 45.625
GRID_ORIGIN_LON = 24.875

EARTH_METERS_PER_DEGREE_LAT = 111_320  # constant everywhere on Earth
SCENE_UNIT_METERS = 1000               # 1 scene unit = 1 km
VERTICAL_EXAGGERATION = 6              # altitude-only multiplier for scene readability

# Fallback standard-atmosphere altitudes (meters), used ONLY if a cell's
# real geopotential_height is missing from the forecast response.
FALLBACK_ALTITUDE_M = {
    400: 7200,
    300: 9200,
    250: 10400,
    200: 11800,
}


def meters_per_degree_longitude(origin_lat_deg: float) -> float:
    """
    Longitude distance shrinks with latitude. This is the one piece of
    real spherical geometry in the whole conversion.
    """
    return EARTH_METERS_PER_DEGREE_LAT * math.cos(math.radians(origin_lat_deg))


def latlon_to_scene_xz(lat: float, lon: float,
                        origin_lat: float = GRID_ORIGIN_LAT,
                        origin_lon: float = GRID_ORIGIN_LON):
    """
    Converts a real-world lat/lon into flat scene coordinates (x, z),
    in kilometers, relative to the fixed grid origin.

    x = east/west offset, z = north/south offset.
    y (altitude) is handled separately by altitude_to_scene_y().
    """
    meters_per_deg_lon = meters_per_degree_longitude(origin_lat)

    x_meters = (lon - origin_lon) * meters_per_deg_lon
    z_meters = (lat - origin_lat) * EARTH_METERS_PER_DEGREE_LAT

    x = x_meters / SCENE_UNIT_METERS
    z = z_meters / SCENE_UNIT_METERS

    return round(x, 3), round(z, 3)


def altitude_to_scene_y(altitude_m: float, exaggeration: float = VERTICAL_EXAGGERATION) -> float:
    """
    Converts a real altitude in meters into a scene y-value in km-based
    scene units, with vertical exaggeration applied so the layers are
    visually distinguishable despite the huge horizontal/vertical scale gap.
    """
    altitude_km = altitude_m / 1000
    y = altitude_km * exaggeration
    return round(y, 3)


def resolve_altitude_m(level_data: dict, pressure_level: int) -> float:
    """
    Prefers the real forecasted geopotential_height for this specific
    cell/level. Falls back to the standard-atmosphere table only if the
    forecast didn't return a value for this field.
    """
    geopotential_m = level_data.get("geopotential_height")
    try:
        geopotential_m = float(geopotential_m)
    except (TypeError, ValueError):
        geopotential_m = None
    if geopotential_m is not None and math.isfinite(geopotential_m) and geopotential_m > 0:
        return geopotential_m
    return FALLBACK_ALTITUDE_M.get(pressure_level)


def attach_scene_coordinates(grid_points: list, pressure_levels: list) -> list:
    """
    Mutates and returns grid_points, adding:
      - point["x"], point["z"]          (shared across all levels of that point)
      - point["levels"][level]["altitude_km"]
      - point["levels"][level]["y"]     (level-specific, since altitude differs per level)
    """
    for point in grid_points:
        x, z = latlon_to_scene_xz(point["lat"], point["lon"])
        point["x"] = x
        point["z"] = z

        for level in pressure_levels:
            level_data = point["levels"].get(level)
            if not level_data:
                continue

            altitude_m = resolve_altitude_m(level_data, level)
            if altitude_m is None:
                level_data["altitude_km"] = None
                level_data["y"] = None
                continue

            level_data["altitude_km"] = round(altitude_m / 1000, 3)
            level_data["y"] = altitude_to_scene_y(altitude_m)

    return grid_points