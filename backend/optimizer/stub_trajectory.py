import math

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


def match_route_waypoint_count(route, target_count):
    """Resample an existing polyline to a requested count without changing its shape."""
    if len(route) < 2 or target_count < 2:
        raise ValueError("route and target_count must each contain at least two points")
    if len(route) == target_count:
        return [dict(point) for point in route]

    cumulative = [0.0]
    for start, end in zip(route, route[1:]):
        altitude_delta = end["altitude_km"] - start["altitude_km"]
        cumulative.append(
            cumulative[-1]
            + math.sqrt(
                (end["x"] - start["x"]) ** 2
                + (end["z"] - start["z"]) ** 2
                + altitude_delta ** 2
            )
        )

    total_distance = cumulative[-1]
    result = []
    segment_index = 0
    for sample_index in range(target_count):
        distance = total_distance * sample_index / (target_count - 1)
        while (segment_index < len(cumulative) - 2
               and cumulative[segment_index + 1] < distance):
            segment_index += 1
        start, end = route[segment_index], route[segment_index + 1]
        segment_length = cumulative[segment_index + 1] - cumulative[segment_index]
        fraction = (
            (distance - cumulative[segment_index]) / segment_length
            if segment_length > 1e-9 else 0.0
        )
        point = dict(start if fraction < 0.5 else end)
        for key in ("lat", "lon", "x", "y", "z", "altitude_km"):
            point[key] = start[key] + (end[key] - start[key]) * fraction
        first_exposure = start.get("exposure_score")
        second_exposure = end.get("exposure_score")
        point["exposure_score"] = (
            first_exposure + (second_exposure - first_exposure) * fraction
            if first_exposure is not None and second_exposure is not None
            else None
        )
        result.append(point)
    return result


generate_stub_route = generate_baseline_route