from grid.coordinates import (
    FALLBACK_ALTITUDE_M,
    altitude_to_scene_y,
    latlon_to_scene_xz,
)
from optimizer.astar import AircraftProfile, annotate_route, extend_with_flight_phases

BASELINE_PRESSURE_LEVEL = 250


def _nearest_baseline_level(lat, lon, grid_points, pressure_level):
    x, z = latlon_to_scene_xz(lat, lon)
    nearest = None
    nearest_distance = float("inf")

    for point in grid_points:
        level_data = point.get("levels").get(
            pressure_level, point.get("levels").get(str(pressure_level))
        )
        if not level_data:
            continue
        point_x, point_z = point.get("x"), point.get("z")
        if point_x is None or point_z is None:
            point_x, point_z = latlon_to_scene_xz(point["lat"], point["lon"])
        distance = (point_x - x) ** 2 + (point_z - z) ** 2
        if distance < nearest_distance:
            nearest = level_data
            nearest_distance = distance

    if nearest is None:
        altitude_m = FALLBACK_ALTITUDE_M[pressure_level]
        return altitude_m / 1000, None

    altitude_km = nearest.get("altitude_km")
    if altitude_km is None:
        altitude_m = nearest.get("geopotential_height")
        if altitude_m is None:
            altitude_m = FALLBACK_ALTITUDE_M[pressure_level]
        altitude_km = altitude_m / 1000
    return float(altitude_km), nearest.get("exposure_score")


def generate_baseline_route(
    origin,
    destination,
    grid_points,
    num_points,
    pressure_level=BASELINE_PRESSURE_LEVEL,
    profile=None,
):
    """
    Straight airport-to-airport baseline at 250 hPa, wrapped in the same
    takeoff/landing phases as the optimized route so both metrics compare
    complete ground-to-ground flights.
    """
    if pressure_level not in FALLBACK_ALTITUDE_M:
        raise ValueError(f"Unsupported baseline pressure level: {pressure_level}")
    if num_points < 1:
        raise ValueError("num_points must be at least one")
    profile = profile or AircraftProfile()

    waypoints = []
    for index in range(num_points + 1):
        fraction = index / num_points
        lat = origin["lat"] + (destination["lat"] - origin["lat"]) * fraction
        lon = origin["lon"] + (destination["lon"] - origin["lon"]) * fraction
        x, z = latlon_to_scene_xz(lat, lon)
        altitude_km, exposure = _nearest_baseline_level(
            lat, lon, grid_points, pressure_level
        )
        waypoints.append(
            {
                "lat": round(lat, 5),
                "lon": round(lon, 5),
                "x": x,
                "y": altitude_to_scene_y(altitude_km * 1000),
                "z": z,
                "altitude_km": altitude_km,
                "pressure_level": pressure_level,
                "exposure_score": exposure,
                "phase": "cruise",
            }
        )

    route = extend_with_flight_phases(
        waypoints, origin, destination, profile, grid_points
    )
    return annotate_route(route, profile)


generate_stub_route = generate_baseline_route