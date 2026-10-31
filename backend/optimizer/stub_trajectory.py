import math

from grid.coordinates import latlon_to_scene_xz, altitude_to_scene_y, FALLBACK_ALTITUDE_M

CRUISE_SPEED_KMH = 800
BASELINE_PRESSURE_LEVEL = 250  # 10.4 km, matches documented default cruise altitude


def _interpolate(start, end, fraction):
    return start + (end - start) * fraction


def _scene_distance_km(a, b):
    return math.sqrt((a["x"] - b["x"]) ** 2 + (a["z"] - b["z"]) ** 2)


def _find_nearest_exposure(point_xz, grid_points, pressure_level):
    """
    Nearest-neighbor lookup against the already-fetched grid, used only to
    attach an approximate exposure score to stub waypoints that don't sit
    exactly on a grid node. Fine for ~300 points; not meant to scale further.
    """
    best, best_dist = None, None
    for gp in grid_points:
        dist = math.sqrt((gp["x"] - point_xz["x"]) ** 2 + (gp["z"] - point_xz["z"]) ** 2)
        if best_dist is None or dist < best_dist:
            best_dist, best = dist, gp

    if best is None:
        return None

    level_data = best["levels"].get(pressure_level)
    return level_data.get("exposure_score") if level_data else None


def generate_stub_route(origin, destination, grid_points, pressure_level=BASELINE_PRESSURE_LEVEL,num_points=10, lateral_offset_km=0.0, altitude_offset_km=0.0):
    """
    TEMPORARY. Produces a straight-line or gently bow-shaped path between
    two airports so the frontend has real-shaped trajectory data to build
    against before real A* exists.

    This is NOT weather-aware pathfinding — it exists purely to validate
    the data contract end to end. Replace with optimizer/astar.py output
    once built; response shape will not change.
    """
    altitude_m = FALLBACK_ALTITUDE_M.get(pressure_level, 10400) + (altitude_offset_km * 1000)

    waypoints = []
    for i in range(num_points + 1):
        fraction = i / num_points
        lat = _interpolate(origin["lat"], destination["lat"], fraction)
        lon = _interpolate(origin["lon"], destination["lon"], fraction)

        # fake sideways bow so "optimized" is visually distinct from
        # "baseline" — not weather-derived, purely cosmetic for now
        lon += lateral_offset_km / 80 * math.sin(fraction * math.pi)

        x, z = latlon_to_scene_xz(lat, lon)
        y = altitude_to_scene_y(altitude_m)

        point = {"lat": round(lat, 5), "lon": round(lon, 5), "x": x, "y": y, "z": z}
        point["exposure_score"] = _find_nearest_exposure(point, grid_points, pressure_level)
        waypoints.append(point)

    return waypoints


def compute_route_metrics(waypoints):
    total_distance_km = sum(
        _scene_distance_km(waypoints[i], waypoints[i + 1]) for i in range(len(waypoints) - 1)
    )
    exposures = [wp["exposure_score"] for wp in waypoints if wp.get("exposure_score") is not None]
    avg_exposure = round(sum(exposures) / len(exposures), 1) if exposures else None
    time_min = round((total_distance_km / CRUISE_SPEED_KMH) * 60, 1)

    return {
        "distance_km": round(total_distance_km, 1),
        "time_min": time_min,
        "avg_exposure": avg_exposure,
    }