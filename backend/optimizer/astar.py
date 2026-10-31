import heapq
import math
import statistics
from dataclasses import dataclass
from itertools import count
from typing import Optional

from grid.coordinates import (
    FALLBACK_ALTITUDE_M,
    VERTICAL_EXAGGERATION,
    altitude_to_scene_y,
    latlon_to_scene_xz,
    resolve_altitude_m,
)

CRUISE_SPEED_KMH = 800
ALTITUDE_CHANGE_PENALTY_MIN = 2
BASELINE_PRESSURE_LEVEL = 250
WEATHER_WEIGHTS = {
    "fastest": 0.5,
    "balanced": 2.0,
    "lower-exposure": 5.0,
}


@dataclass(frozen=True)
class _Node:
    index: tuple[int, int, int]
    pressure_level: int
    lat: float
    lon: float
    x: float
    y: float
    z: float
    altitude_km: float
    exposure_score: Optional[float]


def normalize_mode(mode: str) -> str:
    """Return a canonical preference mode or raise for unsupported input."""
    normalized = mode.strip().lower().replace("_", "-")
    if normalized not in WEATHER_WEIGHTS:
        raise ValueError("mode must be Fastest, Balanced, or Lower-exposure")
    return normalized


def calculate_edge_cost(current, destination, weather_weight: float) -> float:
    """Calculate an edge's routing cost in minutes, excluding missing weather."""
    altitude_delta_km = destination["altitude_km"] - current["altitude_km"]
    distance_km = math.sqrt(
        (destination["x"] - current["x"]) ** 2
        + (destination["z"] - current["z"]) ** 2
        + altitude_delta_km**2
    )
    travel_time_min = distance_km / CRUISE_SPEED_KMH * 60
    exposure = destination.get("exposure_score")
    weather_multiplier = 1 + weather_weight * exposure / 100 if exposure is not None else 1
    altitude_penalty = (
        ALTITUDE_CHANGE_PENALTY_MIN
        if destination["pressure_level"] != current["pressure_level"]
        else 0
    )
    return travel_time_min * weather_multiplier + altitude_penalty


def _level_data(point, pressure_level):
    levels = point.get("levels", {})
    return levels.get(pressure_level, levels.get(str(pressure_level)))


def _altitude_for_level(point, pressure_level, level_data):
    altitude_km = level_data.get("altitude_km")
    if altitude_km is not None:
        try:
            altitude_km = float(altitude_km)
        except (TypeError, ValueError):
            altitude_km = None
        if altitude_km is not None and math.isfinite(altitude_km) and altitude_km > 0:
            return altitude_km
    altitude_m = resolve_altitude_m(level_data, pressure_level)
    if altitude_m is None:
        return None
    return altitude_m / 1000


def _pressure_levels(grid_points):
    levels = set()
    for point in grid_points:
        for level in point.get("levels", {}):
            try:
                levels.add(int(level))
            except (TypeError, ValueError):
                raise ValueError(f"Invalid pressure level: {level!r}")

    def median_altitude(level):
        altitudes = []
        for point in grid_points:
            data = _level_data(point, level)
            if data:
                altitude = _altitude_for_level(point, level, data)
                if altitude is not None:
                    altitudes.append(altitude)
        if altitudes:
            return statistics.median(altitudes)
        return FALLBACK_ALTITUDE_M.get(level, float("inf"))

    return sorted(levels, key=lambda level: (median_altitude(level), level))


def _build_nodes(grid_points):
    if not grid_points:
        raise ValueError("The weather grid is empty")

    pressure_levels = _pressure_levels(grid_points)
    if not pressure_levels:
        raise ValueError("The weather grid has no pressure levels")

    latitudes = sorted({float(point["lat"]) for point in grid_points})
    longitudes = sorted({float(point["lon"]) for point in grid_points})
    row_by_lat = {lat: row for row, lat in enumerate(latitudes)}
    col_by_lon = {lon: col for col, lon in enumerate(longitudes)}
    layer_by_level = {level: layer for layer, level in enumerate(pressure_levels)}
    nodes = {}

    for point in grid_points:
        lat, lon = float(point["lat"]), float(point["lon"])
        x, z = point.get("x"), point.get("z")
        if x is None or z is None:
            x, z = latlon_to_scene_xz(lat, lon)
        else:
            x, z = float(x), float(z)

        for pressure_level in pressure_levels:
            level_data = _level_data(point, pressure_level)
            if not level_data:
                continue
            altitude_km = _altitude_for_level(point, pressure_level, level_data)
            if altitude_km is None:
                continue

            exposure = level_data.get("exposure_score")
            if exposure is not None:
                try:
                    exposure = float(exposure)
                except (TypeError, ValueError):
                    raise ValueError("Exposure scores must be numbers or null")
                if not math.isfinite(exposure) or not 0 <= exposure <= 100:
                    raise ValueError("Exposure scores must be between 0 and 100")

            y = level_data.get("y")
            if y is None:
                y = altitude_to_scene_y(altitude_km * 1000)
            index = (
                row_by_lat[lat],
                col_by_lon[lon],
                layer_by_level[pressure_level],
            )
            nodes[index] = _Node(
                index=index,
                pressure_level=pressure_level,
                lat=lat,
                lon=lon,
                x=x,
                y=float(y),
                z=z,
                altitude_km=altitude_km,
                exposure_score=exposure,
            )

    if not nodes:
        raise ValueError("The weather grid has no usable nodes")
    return nodes, pressure_levels, row_by_lat, col_by_lon


def _neighbors(index, nodes):
    row, col, layer = index
    for row_delta in (-1, 0, 1):
        for col_delta in (-1, 0, 1):
            for layer_delta in (-1, 0, 1):
                if row_delta == col_delta == layer_delta == 0:
                    continue
                neighbor_index = (row + row_delta, col + col_delta, layer + layer_delta)
                neighbor = nodes.get(neighbor_index)
                if neighbor is not None:
                    yield neighbor


def _distance_km(a, b):
    altitude_delta_km = b.altitude_km - a.altitude_km
    return math.sqrt((b.x - a.x) ** 2 + (b.z - a.z) ** 2 + altitude_delta_km**2)


def _heuristic(node, goal):
    return _distance_km(node, goal) / CRUISE_SPEED_KMH * 60


def _nearest_node(nodes, airport, preferred_layer):
    airport_x, airport_z = latlon_to_scene_xz(airport["lat"], airport["lon"])
    candidates = (node for node in nodes.values() if node.index[2] == preferred_layer)
    nearest = min(
        candidates,
        key=lambda node: ((node.x - airport_x) ** 2 + (node.z - airport_z) ** 2, node.index),
        default=None,
    )
    if nearest is None:
        raise ValueError("The weather grid has no nodes at its lowest altitude level")
    return nearest


def _route_waypoint(node, lat=None, lon=None):
    if lat is None:
        lat, lon = node.lat, node.lon
        x, z = node.x, node.z
    else:
        x, z = latlon_to_scene_xz(lat, lon)
    return {
        "lat": lat,
        "lon": lon,
        "x": x,
        "y": node.y,
        "z": z,
        "altitude_km": node.altitude_km,
        "pressure_level": node.pressure_level,
        "exposure_score": node.exposure_score,
    }


def estimate_route_position(route, progress):
    """Estimate the aircraft position at normalized distance along its route."""
    if not route:
        raise ValueError("route must contain at least one waypoint")
    if not 0 <= progress <= 1:
        raise ValueError("progress must be between 0 and 1")
    if len(route) == 1:
        return dict(route[0])

    def altitude(waypoint):
        value = waypoint.get("altitude_km")
        return float(value) if value is not None else waypoint["y"] / VERTICAL_EXAGGERATION

    lengths = []
    total_length = 0.0
    for start, end in zip(route, route[1:]):
        length = math.sqrt(
            (end["x"] - start["x"]) ** 2
            + (end["z"] - start["z"]) ** 2
            + (altitude(end) - altitude(start)) ** 2
        )
        lengths.append(length)
        total_length += length
    if total_length == 0:
        return dict(route[0])

    remaining = total_length * progress
    for index, length in enumerate(lengths):
        start, end = route[index], route[index + 1]
        if remaining <= length or index == len(lengths) - 1:
            fraction = remaining / length if length else 0.0
            lat = start["lat"] + (end["lat"] - start["lat"]) * fraction
            lon = start["lon"] + (end["lon"] - start["lon"]) * fraction
            altitude_km = altitude(start) + (altitude(end) - altitude(start)) * fraction
            x, z = latlon_to_scene_xz(lat, lon)
            pressure_level = (
                start.get("pressure_level")
                if fraction < 0.5
                else end.get("pressure_level", start.get("pressure_level"))
            )
            return {
                "lat": lat,
                "lon": lon,
                "x": x,
                "y": altitude_to_scene_y(altitude_km * 1000),
                "z": z,
                "altitude_km": altitude_km,
                "pressure_level": pressure_level,
                "exposure_score": start.get("exposure_score"),
                "route_progress": progress,
            }
        remaining -= length

    return dict(route[-1])


def assess_route_weather_change(previous_grid, updated_grid, route, progress):
    """Compare exposure on the remaining route and flag material increases."""
    current_position = estimate_route_position(route, progress)
    total_distance = sum(
        _waypoint_distance(start, end)
        for start, end in zip(route, route[1:])
    )
    remaining_distance = 0.0
    samples = [current_position]
    for start, end in zip(route, route[1:]):
        segment_distance = _waypoint_distance(start, end)
        remaining_distance += segment_distance
        if total_distance and remaining_distance / total_distance > progress:
            samples.append(end)

    changes = []
    for waypoint in samples:
        pressure_level = waypoint.get("pressure_level")
        previous_score = _nearest_exposure(previous_grid, waypoint, pressure_level)
        updated_score = _nearest_exposure(updated_grid, waypoint, pressure_level)
        if previous_score is None or updated_score is None:
            continue
        delta = updated_score - previous_score
        changes.append(
            {
                "lat": waypoint["lat"],
                "lon": waypoint["lon"],
                "level_hpa": pressure_level,
                "previous_exposure": previous_score,
                "updated_exposure": updated_score,
                "increase": round(delta, 1),
            }
        )

    increases = [change["increase"] for change in changes]
    affected = [change for change in changes if change["increase"] >= 25]
    average_increase = sum(increases) / len(increases) if increases else 0.0
    maximum_increase = max(increases, default=0.0)
    drastic = maximum_increase >= 50 or (
        len(affected) >= 2 and average_increase >= 25
    )
    return {
        "drastic": drastic,
        "threshold": {"single_waypoint_increase": 50, "average_increase": 25},
        "sample_count": len(changes),
        "affected_waypoint_count": len(affected),
        "average_exposure_increase": round(average_increase, 1),
        "maximum_exposure_increase": round(maximum_increase, 1),
        "affected_waypoints": affected,
    }


def _waypoint_distance(start, end):
    start_altitude = start.get("altitude_km")
    if start_altitude is None:
        start_altitude = start["y"] / VERTICAL_EXAGGERATION
    end_altitude = end.get("altitude_km")
    if end_altitude is None:
        end_altitude = end["y"] / VERTICAL_EXAGGERATION
    return math.sqrt(
        (end["x"] - start["x"]) ** 2
        + (end["z"] - start["z"]) ** 2
        + (end_altitude - start_altitude) ** 2
    )


def _nearest_exposure(grid, waypoint, pressure_level):
    if pressure_level is None or not grid:
        return None
    nearest = None
    nearest_distance = float("inf")
    for point in grid:
        levels = point.get("levels", {})
        level_data = levels.get(pressure_level, levels.get(str(pressure_level)))
        if not level_data:
            continue
        x, z = point.get("x"), point.get("z")
        if x is None or z is None:
            x, z = latlon_to_scene_xz(point["lat"], point["lon"])
        distance = (x - waypoint["x"]) ** 2 + (z - waypoint["z"]) ** 2
        if distance < nearest_distance:
            nearest_distance = distance
            nearest = level_data.get("exposure_score")
    return nearest


def find_path(grid_points, origin, destination, mode="Balanced", start_position=None):
    """Find a weather-aware route through the 26-connected forecast grid."""
    canonical_mode = normalize_mode(mode)
    weather_weight = WEATHER_WEIGHTS[canonical_mode]
    nodes, pressure_levels, _, _ = _build_nodes(grid_points)
    preferred_level = min(
        range(len(pressure_levels)),
        key=lambda layer: min(
            (node.altitude_km for node in nodes.values() if node.index[2] == layer),
            default=float("inf"),
        ),
    )
    search_start = start_position or origin
    start_layer = preferred_level
    if start_position and start_position.get("pressure_level") in pressure_levels:
        start_layer = pressure_levels.index(start_position["pressure_level"])
    start = _nearest_node(nodes, search_start, start_layer)
    goal = _nearest_node(nodes, destination, preferred_level)

    tie_breaker = count()
    open_set = [(_heuristic(start, goal), next(tie_breaker), start.index)]
    costs = {start.index: 0.0}
    previous = {}
    closed = set()

    while open_set:
        _, _, current_index = heapq.heappop(open_set)
        if current_index in closed:
            continue
        if current_index == goal.index:
            break
        closed.add(current_index)
        current = nodes[current_index]

        for neighbor in _neighbors(current_index, nodes):
            if neighbor.index in closed:
                continue
            current_cost = costs[current_index]
            edge_cost = calculate_edge_cost(
                {
                    "x": current.x,
                    "z": current.z,
                    "altitude_km": current.altitude_km,
                    "pressure_level": current.pressure_level,
                },
                {
                    "x": neighbor.x,
                    "z": neighbor.z,
                    "altitude_km": neighbor.altitude_km,
                    "pressure_level": neighbor.pressure_level,
                    "exposure_score": neighbor.exposure_score,
                },
                weather_weight,
            )
            tentative_cost = current_cost + edge_cost
            if tentative_cost < costs.get(neighbor.index, float("inf")):
                costs[neighbor.index] = tentative_cost
                previous[neighbor.index] = current_index
                total_estimate = tentative_cost + _heuristic(neighbor, goal)
                heapq.heappush(
                    open_set, (total_estimate, next(tie_breaker), neighbor.index)
                )
    else:
        raise ValueError("No route connects the origin and destination on this grid")

    path_indices = [goal.index]
    while path_indices[-1] != start.index:
        predecessor = previous.get(path_indices[-1])
        if predecessor is None:
            raise ValueError("Unable to reconstruct the route through the weather grid")
        path_indices.append(predecessor)
    path_indices.reverse()

    start_waypoint = _route_waypoint(start, search_start["lat"], search_start["lon"])
    if start_position:
        start_waypoint.update(
            {
                "y": start_position.get("y", start_waypoint["y"]),
                "altitude_km": start_position.get("altitude_km", start_waypoint["altitude_km"]),
                "pressure_level": start_position.get("pressure_level", start.pressure_level),
            }
        )
    route = [start_waypoint]
    route.extend(_route_waypoint(nodes[index]) for index in path_indices)
    route.append(_route_waypoint(goal, destination["lat"], destination["lon"]))
    return route


def compute_route_metrics(waypoints):
    total_distance_km = 0.0
    total_time_min = 0.0
    for start, end in zip(waypoints, waypoints[1:]):
        start_altitude = start.get("altitude_km")
        if start_altitude is None:
            start_altitude = start["y"] / VERTICAL_EXAGGERATION
        end_altitude = end.get("altitude_km")
        if end_altitude is None:
            end_altitude = end["y"] / VERTICAL_EXAGGERATION
        distance_km = math.sqrt(
            (end["x"] - start["x"]) ** 2
            + (end["z"] - start["z"]) ** 2
            + (end_altitude - start_altitude) ** 2
        )
        total_distance_km += distance_km
        total_time_min += distance_km / CRUISE_SPEED_KMH * 60

    exposures = [
        waypoint["exposure_score"]
        for waypoint in waypoints
        if waypoint.get("exposure_score") is not None
    ]
    return {
        "distance_km": round(total_distance_km, 1),
        "time_min": round(total_time_min, 1),
        "avg_exposure": round(sum(exposures) / len(exposures), 1) if exposures else None,
    }


def find_avoided_high_exposure_cells(grid_points, baseline_route, optimized_route):
    """Return high-exposure baseline cells absent from the optimized path."""
    nodes, _, _, _ = _build_nodes(grid_points)
    baseline_level = BASELINE_PRESSURE_LEVEL
    optimized_cells = set()
    for waypoint in optimized_route:
        matching = _nearest_grid_cell(nodes, waypoint)
        if matching is not None:
            optimized_cells.add(
                (matching.lat, matching.lon, matching.pressure_level)
            )

    avoided = {}
    for waypoint in baseline_route:
        matching = _nearest_grid_cell(nodes, waypoint, baseline_level)
        if (
            matching is not None
            and matching.exposure_score is not None
            and matching.exposure_score > 50
            and (matching.lat, matching.lon, matching.pressure_level)
            not in optimized_cells
        ):
            key = (matching.lat, matching.lon, matching.pressure_level)
            avoided[key] = {
                "type": "high_exposure",
                "level_hpa": matching.pressure_level,
                "lat": matching.lat,
                "lon": matching.lon,
                "exposure_score": matching.exposure_score,
            }
    return sorted(
        avoided.values(),
        key=lambda cell: (-cell["exposure_score"], cell["lat"], cell["lon"]),
    )[:10]


def _nearest_grid_cell(nodes, waypoint, pressure_level=None):
    candidates = [
        node
        for node in nodes.values()
        if pressure_level is None or node.pressure_level == pressure_level
    ]
    if not candidates:
        return None
    x, z = latlon_to_scene_xz(waypoint["lat"], waypoint["lon"])
    return min(
        candidates,
        key=lambda node: (
            (node.x - x) ** 2
            + (node.z - z) ** 2
            + (
                (node.y - waypoint["y"]) / VERTICAL_EXAGGERATION
            ) ** 2,
            node.index,
        ),
    )
