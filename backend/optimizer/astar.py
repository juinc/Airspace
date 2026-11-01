import heapq
import math
import statistics
from dataclasses import dataclass, asdict
from itertools import count
from typing import Optional

from grid.coordinates import latlon_to_scene_xz, altitude_to_scene_y

# Default aircraft assumptions — a generic narrowbody jet.
# Simulation parameters, NOT aircraft-specific performance data.
CRUISE_SPEED_KMH = 800
CLIMB_RATE_M_PER_MIN = 600
DESCENT_RATE_M_PER_MIN = 600
ALTITUDE_CHANGE_PENALTY_MIN = 0.5
REFERENCE_WEIGHT_KG = 73000.0
FUEL_BURN_KG_PER_HOUR = 2500.0
FUEL_CAPACITY_KG = 20000.0
MAX_ALTITUDE_KM = 12.5
FUEL_RESERVE_FRACTION = 0.25

BASELINE_PRESSURE_LEVEL = 250
WEATHER_WEIGHTS = {
    "fastest": 0.5,
    "balanced": 2.0,
    "lower-exposure": 5.0,
}

CLIMB_GRADIENT_KM_PER_KM = 14.0    # was 12 — perceived angle ~16° with 4x exaggeration
DESCENT_GRADIENT_KM_PER_KM = 16.0  # was 14
CLIMB_DISTANCE_CAP = 0.40          # was 0.35 — longer runways of sky to climb through
DESCENT_DISTANCE_CAP = 0.40
SAMPLE_SPACING_KM = 8.0           # dense resampling -> smooth rendered curve
GROUND_ROLL_KM = 1.5              # flat runway roll before rotation
PHASE_EASE_FRACTION = 0.20        # 20% ease in/out, 60% constant-rate
MERGE_TOLERANCE_KM = 0.4

@dataclass(frozen=True)
class AircraftProfile:
    """Aircraft parameters settable from the frontend. Modeled assumptions."""

    cruise_speed_kmh: float = CRUISE_SPEED_KMH
    climb_rate_m_per_min: float = CLIMB_RATE_M_PER_MIN
    descent_rate_m_per_min: float = DESCENT_RATE_M_PER_MIN
    altitude_change_penalty_min: float = ALTITUDE_CHANGE_PENALTY_MIN
    weight_kg: float = REFERENCE_WEIGHT_KG
    reference_weight_kg: float = REFERENCE_WEIGHT_KG
    fuel_burn_kg_per_hour: float = FUEL_BURN_KG_PER_HOUR
    fuel_capacity_kg: float = FUEL_CAPACITY_KG
    max_altitude_km: float = MAX_ALTITUDE_KM

    def __post_init__(self):
        positive_fields = (
            "cruise_speed_kmh",
            "climb_rate_m_per_min",
            "descent_rate_m_per_min",
            "weight_kg",
            "reference_weight_kg",
            "fuel_burn_kg_per_hour",
            "fuel_capacity_kg",
            "max_altitude_km",
        )
        for field in positive_fields:
            if getattr(self, field) <= 0:
                raise ValueError(f"{field} must be positive")
        if self.altitude_change_penalty_min < 0:
            raise ValueError("altitude_change_penalty_min must be non-negative")

    @property
    def weight_ratio(self) -> float:
        """Heavier than reference -> climbs slower. Clamped to stay sane."""
        return min(1.5, max(0.5, self.reference_weight_kg / self.weight_kg))

    @property
    def effective_climb_rate_m_per_min(self) -> float:
        return self.climb_rate_m_per_min * self.weight_ratio

    @property
    def effective_descent_rate_m_per_min(self) -> float:
        return self.descent_rate_m_per_min * self.weight_ratio

    @property
    def effective_fuel_burn_kg_per_hour(self) -> float:
        """Heavier aircraft burn more fuel per hour. Clamped linear model."""
        return self.fuel_burn_kg_per_hour * min(2.0, max(0.5, self.weight_kg / self.reference_weight_kg))

    def as_dict(self) -> dict:
        return asdict(self)


def normalize_mode(mode: str) -> str:
    """Return a canonical preference mode or raise for unsupported input."""
    normalized = mode.strip().lower().replace("_", "-")
    if normalized not in WEATHER_WEIGHTS:
        raise ValueError("mode must be Fastest, Balanced, or Lower-exposure")
    return normalized


def edge_travel_time_min(current, destination, profile: AircraftProfile) -> float:
    """
    Realistic per-edge travel time. The aircraft climbs/descends WHILE flying
    forward, so the edge takes the LONGER of horizontal cruise time and
    vertical transit time — not their sum, not just the horizontal leg.
    """
    horizontal_km = math.hypot(
        destination["x"] - current["x"],
        destination["z"] - current["z"],
    )
    cruise_time_min = horizontal_km / profile.cruise_speed_kmh * 60

    altitude_delta_km = destination["altitude_km"] - current["altitude_km"]
    if abs(altitude_delta_km) > 1e-9:
        rate = (
            profile.effective_climb_rate_m_per_min
            if altitude_delta_km > 0
            else profile.effective_descent_rate_m_per_min
        )
        vertical_time_min = abs(altitude_delta_km) * 1000 / rate
        return max(cruise_time_min, vertical_time_min)
    return cruise_time_min


def calculate_edge_cost(current, destination, weather_weight: float,
                        profile: Optional[AircraftProfile] = None) -> float:
    """J_edge = T_edge * (1 + lambda * R / 100) + A, with T climb-aware."""
    profile = profile or AircraftProfile()
    travel_time_min = edge_travel_time_min(current, destination, profile)

    exposure = destination.get("exposure_score")
    weather_multiplier = 1 + weather_weight * exposure / 100 if exposure is not None else 1

    altitude_penalty = (
        profile.altitude_change_penalty_min
        if destination.get("pressure_level") != current.get("pressure_level")
        else 0
    )
    return travel_time_min * weather_multiplier + altitude_penalty


# ---------------------------------------------------------------------------
# Grid -> node graph
# ---------------------------------------------------------------------------

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


def _heuristic(node, goal, profile):
    # Horizontal-distance-only: guaranteed admissible — climb time and
    # weather terms only ever ADD cost, never subtract.
    horizontal_km = math.hypot(goal.x - node.x, goal.z - node.z)
    return horizontal_km / profile.cruise_speed_kmh * 60


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
        "phase": "cruise",
    }


# ---------------------------------------------------------------------------
# Takeoff / landing phase construction — FMS-style
# ---------------------------------------------------------------------------

def _surface_exposure_lookup(grid_points):
    """Nearest-cell exposure samples for climb/descent waypoints.

    AIFS provides no data below the lowest pressure level, so phase
    waypoints use the LOWEST available forecast level — the closest data
    to that altitude. Never fabricated, never zero.
    """
    try:
        lowest_level = _pressure_levels(grid_points)[0]
    except ValueError:
        return []
    lookup = []
    for point in grid_points:
        data = _level_data(point, lowest_level)
        if not data:
            continue
        x, z = point.get("x"), point.get("z")
        if x is None or z is None:
            x, z = latlon_to_scene_xz(point["lat"], point["lon"])
        lookup.append((float(x), float(z), data.get("exposure_score")))
    return lookup


def _nearest_surface_exposure(lookup, x, z):
    nearest = None
    nearest_distance = float("inf")
    for cell_x, cell_z, exposure in lookup:
        distance = (cell_x - x) ** 2 + (cell_z - z) ** 2
        if distance < nearest_distance:
            nearest_distance = distance
            nearest = exposure
    return nearest


def _phase_waypoint(lat, lon, x, z, altitude_km, exposure, phase):
    return {
        "lat": round(lat, 5),
        "lon": round(lon, 5),
        "x": x,
        "z": z,
        "y": altitude_to_scene_y(altitude_km * 1000),
        "altitude_km": round(altitude_km, 3),
        "pressure_level": None,
        "exposure_score": exposure,
        "phase": phase,
    }


def _smoothstep(u):
    if u <= 0:
        return 0.0
    if u >= 1:
        return 1.0
    return u * u * (3 - 2 * u)


def _phase_gradient(profile, rate_m_per_min, bounds):
    """km horizontal per km vertical, from cruise speed vs vertical rate."""
    rate_kmh = rate_m_per_min * 0.06
    if rate_kmh <= 1e-9:
        return bounds[1]
    return max(bounds[0], min(bounds[1], profile.cruise_speed_kmh / rate_kmh))


def _phase_altitude_fraction(u: float, ease: float = PHASE_EASE_FRACTION) -> float:
    """
    Constant-rate climb/descent shape: linear altitude-vs-distance (what an
    FMS flies) with short quadratic ease-in (rotation) and ease-out
    (level-off / flare). Zero slope at both ends, max slope only 1.25x average.
    """
    if u <= 0.0:
        return 0.0
    if u >= 1.0:
        return 1.0
    slope = 1.0 / (1.0 - ease)
    if u < ease:
        return slope * u * u / (2.0 * ease)
    if u > 1.0 - ease:
        return 1.0 - slope * (1.0 - u) * (1.0 - u) / (2.0 * ease)
    return slope * (u - ease / 2.0)

def _profile_waypoint(lat, lon, x, z, altitude_km, exposure, phase):
    return {
        "lat": round(lat, 5),
        "lon": round(lon, 5),
        "x": round(x, 3),
        "z": round(z, 3),
        "altitude_km": round(altitude_km, 3),
        "y": round(altitude_to_scene_y(altitude_km * 1000), 3),
        "surface_exposure": exposure,
        "phase": phase,
        "pressure_level": None,
    }

def _polyline_points(route, origin, destination):
    """Airport -> A* nodes -> airport, as one polyline with altitudes."""
    origin_x, origin_z = latlon_to_scene_xz(origin["lat"], origin["lon"])
    dest_x, dest_z = latlon_to_scene_xz(destination["lat"], destination["lon"])
    points = [{
        "lat": origin["lat"], "lon": origin["lon"],
        "x": origin_x, "z": origin_z, "altitude_km": 0.0,
    }]
    for node in route:
        points.append({
            "lat": node["lat"], "lon": node["lon"],
            "x": node["x"], "z": node["z"],
            "altitude_km": node.get("altitude_km") or 0.0,
        })
    points.append({
        "lat": destination["lat"], "lon": destination["lon"],
        "x": dest_x, "z": dest_z, "altitude_km": 0.0,
    })
    return points

def _cumulative_distances(points):
    dists = [0.0]
    for i in range(1, len(points)):
        dists.append(dists[-1] + math.hypot(
            points[i]["x"] - points[i - 1]["x"],
            points[i]["z"] - points[i - 1]["z"],
        ))
    return dists

def _interp_at(points, dists, s):
    """Linear interpolation of (lat, lon, x, z, altitude_km) at distance s."""
    if s <= 0.0:
        p = points[0]
        return p["lat"], p["lon"], p["x"], p["z"], p["altitude_km"]
    if s >= dists[-1]:
        p = points[-1]
        return p["lat"], p["lon"], p["x"], p["z"], p["altitude_km"]
    for i in range(len(dists) - 1):
        if dists[i] <= s <= dists[i + 1]:
            span = dists[i + 1] - dists[i]
            t = (s - dists[i]) / span if span > 1e-9 else 0.0
            a, b = points[i], points[i + 1]
            return (
                a["lat"] + (b["lat"] - a["lat"]) * t,
                a["lon"] + (b["lon"] - a["lon"]) * t,
                a["x"] + (b["x"] - a["x"]) * t,
                a["z"] + (b["z"] - a["z"]) * t,
                a["altitude_km"] + (b["altitude_km"] - a["altitude_km"]) * t,
            )
    p = points[-1]
    return p["lat"], p["lon"], p["x"], p["z"], p["altitude_km"]


def _build_takeoff(origin, cruise_route, profile, lookup):
    """
    Ground roll at the airport, rotation, then a constant-rate climb that
    tops out EXACTLY at the first A* node within reach. On short corridors
    the climb distance is capped at CLIMB_ROUTE_FRACTION of the corridor and
    the gradient simply becomes shallower (thrust-reduced climb).
    Returns (samples, target_index).
    """
    origin_x, origin_z = latlon_to_scene_xz(origin["lat"], origin["lon"])
    first_alt = cruise_route[0]["altitude_km"]
    gradient = _phase_gradient(
        profile, profile.effective_climb_rate_m_per_min, CLIMB_GRADIENT_BOUNDS
    )
    corridor_km = math.hypot(
        cruise_route[-1]["x"] - origin_x,
        cruise_route[-1]["z"] - origin_z,
    )
    climb_dist = min(
        max(1.0, first_alt * gradient),
        max(1.0, corridor_km * CLIMB_ROUTE_FRACTION),
    )

    target_index = len(cruise_route) - 1
    for index, waypoint in enumerate(cruise_route):
        if math.hypot(waypoint["x"] - origin_x, waypoint["z"] - origin_z) >= climb_dist:
            target_index = index
            break
    target = cruise_route[target_index]
    target_alt = target["altitude_km"]

    total_km = math.hypot(target["x"] - origin_x, target["z"] - origin_z)
    if total_km <= 1e-6:
        return [], 0
    roll_fraction = min(0.4, GROUND_ROLL_KM / total_km)

    samples = []
    for i in range(0, PHASE_SAMPLES + 1):   # t=0 included: the airport itself
        t = i / PHASE_SAMPLES
        u = 0.0 if t <= roll_fraction else (t - roll_fraction) / (1 - roll_fraction)
        lat = origin["lat"] + (target["lat"] - origin["lat"]) * t
        lon = origin["lon"] + (target["lon"] - origin["lon"]) * t
        x = origin_x + (target["x"] - origin_x) * t
        z = origin_z + (target["z"] - origin_z) * t
        altitude_km = target_alt * _phase_altitude_fraction(u)
        samples.append(_phase_waypoint(
            lat, lon, x, z, altitude_km,
            _nearest_surface_exposure(lookup, x, z),
            "takeoff",
        ))
    # Drop the final sample: it coincides with the target node, whose own
    # waypoint (with exposure/level metadata) closes the phase.
    return samples[:-1], target_index


def _build_landing(destination, cruise_route, profile, lookup):
    """
    Top-of-descent selection, FMS-style: walk BACKWARD from the destination
    until the route has enough horizontal distance for a clean glide, then
    descend from that node with a constant-rate profile — gentle push-over
    at the top, flare to zero slope at touchdown on the airport. The descent
    distance is capped at DESCENT_ROUTE_FRACTION of the corridor.
    Returns (samples, source_index).
    """
    dest_x, dest_z = latlon_to_scene_xz(destination["lat"], destination["lon"])
    source_alt = cruise_route[-1]["altitude_km"]
    gradient = _phase_gradient(
        profile, profile.effective_descent_rate_m_per_min, DESCENT_GRADIENT_BOUNDS
    )
    corridor_km = math.hypot(
        dest_x - cruise_route[0]["x"],
        dest_z - cruise_route[0]["z"],
    )
    descent_dist = min(
        max(1.0, source_alt * gradient),
        max(1.0, corridor_km * DESCENT_ROUTE_FRACTION),
    )

    source_index = 0
    for index in range(len(cruise_route) - 1, -1, -1):
        waypoint = cruise_route[index]
        if math.hypot(waypoint["x"] - dest_x, waypoint["z"] - dest_z) >= descent_dist:
            source_index = index
            break
    source = cruise_route[source_index]

    total_km = math.hypot(dest_x - source["x"], dest_z - source["z"])
    if total_km <= 1e-6:
        return [], len(cruise_route) - 1

    samples = []
    for i in range(1, PHASE_SAMPLES + 1):
        t = i / PHASE_SAMPLES
        lat = source["lat"] + (destination["lat"] - source["lat"]) * t
        lon = source["lon"] + (destination["lon"] - source["lon"]) * t
        x = source["x"] + (dest_x - source["x"]) * t
        z = source["z"] + (dest_z - source["z"]) * t
        altitude_km = source_alt * _phase_altitude_fraction(1 - t)
        samples.append(_phase_waypoint(
            lat, lon, x, z, altitude_km,
            _nearest_surface_exposure(lookup, x, z),
            "landing",
        ))
    return samples, source_index


def extend_with_flight_phases(route, origin, destination, profile, grid_points,
                              include_takeoff=True, include_landing=True):
    """
    Wraps a cruise-altitude A* route in a complete, continuously-smooth flight:

      ground roll at the origin airport -> constant-rate climb -> the A*
      nodes' own altitude profile (level changes A* chose are preserved)
      -> constant-rate descent with flare -> touchdown at the destination.

    The route is resampled every SAMPLE_SPACING_KM and merged with the
    original A* nodes (which keep their pressure_level / exposure metadata
    for the inspector), with node altitudes clamped by the envelopes.
    """
    profile = profile or AircraftProfile()
    route = [dict(waypoint) for waypoint in route]
    if len(route) < 2:
        return route
    lookup = _surface_exposure_lookup(grid_points)

    points = _polyline_points(route, origin, destination)
    dists = _cumulative_distances(points)
    total_km = dists[-1]
    if total_km <= 1e-6:
        return route

    def base_alt(s):
        return _interp_at(points, dists, s)[4]

    first_alt = points[1]["altitude_km"]
    last_alt = points[-2]["altitude_km"]

    climb_dist = min(
        first_alt * CLIMB_GRADIENT_KM_PER_KM,
        CLIMB_DISTANCE_CAP * total_km,
    ) if include_takeoff else 0.0
    descent_dist = min(
        last_alt * DESCENT_GRADIENT_KM_PER_KM,
        DESCENT_DISTANCE_CAP * total_km,
    ) if include_landing else 0.0
    if climb_dist + descent_dist > total_km:
        scale = total_km / max(1e-6, climb_dist + descent_dist)
        climb_dist *= scale
        descent_dist *= scale

    climb_top_alt = base_alt(climb_dist)
    descent_bottom_alt = base_alt(total_km - descent_dist)

    def altitude_at(s):
        alt = base_alt(s)
        if include_takeoff and climb_dist > 0.0 and s < climb_dist:
            roll = min(GROUND_ROLL_KM, climb_dist * 0.3)
            if s <= roll:
                alt = 0.0
            else:
                u = (s - roll) / max(1e-6, climb_dist - roll)
                alt = min(alt, climb_top_alt * _phase_altitude_fraction(u))
        if include_landing and descent_dist > 0.0 and s > total_km - descent_dist:
            u = (total_km - s) / descent_dist
            alt = min(alt, descent_bottom_alt * _phase_altitude_fraction(u))
        return alt

    def phase_at(s):
        if include_takeoff and climb_dist > 0.0 and s < climb_dist * 0.999:
            return "takeoff"
        if include_landing and descent_dist > 0.0 and s > total_km - descent_dist * 0.999:
            return "landing"
        return "cruise"

    entries = []  # (distance, waypoint_dict, is_astar_node)

    n_steps = max(4, math.ceil(total_km / SAMPLE_SPACING_KM))
    for k in range(n_steps + 1):
        s = total_km * k / n_steps
        lat, lon, x, z, _ = _interp_at(points, dists, s)
        entries.append((s, _profile_waypoint(
            lat, lon, x, z, altitude_at(s),
            _nearest_surface_exposure(lookup, x, z),
            phase_at(s),
        ), False))

    for i, node in enumerate(route):
        s = dists[i + 1]
        lat, lon, x, z, _ = _interp_at(points, dists, s)
        node["altitude_km"] = round(altitude_at(s), 3)
        node["y"] = round(altitude_to_scene_y(node["altitude_km"] * 1000), 3)
        node["phase"] = phase_at(s)
        if node.get("surface_exposure") is None:
            node["surface_exposure"] = _nearest_surface_exposure(lookup, x, z)
        entries.append((s, node, True))

    entries.sort(key=lambda entry: entry[0])

    result = []
    last_kept_s = None
    for s, waypoint, is_node in entries:
        if last_kept_s is not None and (s - last_kept_s) <= MERGE_TOLERANCE_KM:
            if is_node and result and result[-1].get("pressure_level") is None:
                result.pop()  # co-located A* node wins over the bare sample
            elif not is_node:
                continue    # sample too close to the previous kept point
        result.append(waypoint)
        last_kept_s = s

    return result

def annotate_route(route, grid_points=None, default_phase="cruise"):
    """
    Fills in display/metadata fields on an already-computed route
    (used by the baseline generator, whose straight-line path doesn't
    go through extend_with_flight_phases). Mutates and returns the route.
    """
    lookup = _surface_exposure_lookup(grid_points) if grid_points else None

    for waypoint in route:
        if waypoint.get("surface_exposure") is None:
            if lookup is not None:
                waypoint["surface_exposure"] = _nearest_surface_exposure(
                    lookup, waypoint["x"], waypoint["z"]
                )
            else:
                waypoint["surface_exposure"] = 0
        if waypoint.get("phase") is None:
            waypoint["phase"] = default_phase
        if waypoint.get("pressure_level") is None:
            waypoint["pressure_level"] = None
    return route

# ---------------------------------------------------------------------------
# Replan helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# A* search
# ---------------------------------------------------------------------------

def find_path(grid_points, origin, destination, mode="Balanced",
              start_position=None, profile=None):
    """Find a weather-aware route through the 26-connected forecast grid.

    The returned route is a COMPLETE flight: ground roll and climb out of
    the origin airport, the A*-optimized cruise path, and a descent with
    flare onto the destination airport. When start_position is given
    (in-flight replan), the route resumes from that airborne position and
    no takeoff phase is added.
    """
    canonical_mode = normalize_mode(mode)
    weather_weight = WEATHER_WEIGHTS[canonical_mode]
    profile = profile or AircraftProfile()

    nodes, pressure_levels, _, _ = _build_nodes(grid_points)

    # Service ceiling: drop every layer the aircraft cannot physically reach.
    reachable = {
        index: node
        for index, node in nodes.items()
        if node.altitude_km <= profile.max_altitude_km + 1e-9
    }
    if not reachable:
        raise ValueError(
            f"No grid layers below the aircraft ceiling of {profile.max_altitude_km} km"
        )
    nodes = reachable

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
    open_set = [(_heuristic(start, goal, profile), next(tie_breaker), start.index)]
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
                profile,
            )
            tentative_cost = current_cost + edge_cost
            if tentative_cost < costs.get(neighbor.index, float("inf")):
                costs[neighbor.index] = tentative_cost
                previous[neighbor.index] = current_index
                total_estimate = tentative_cost + _heuristic(neighbor, goal, profile)
                heapq.heappush(
                    open_set, (total_estimate, next(tie_breaker), neighbor.index)
                )
    else:
        raise ValueError(
            "No route connects the origin and destination on this grid "
            f"with a ceiling of {profile.max_altitude_km} km"
        )

    path_indices = [goal.index]
    while path_indices[-1] != start.index:
        predecessor = previous.get(path_indices[-1])
        if predecessor is None:
            raise ValueError("Unable to reconstruct the route through the weather grid")
        path_indices.append(predecessor)
    path_indices.reverse()

    # Cruise path: grid nodes only. The ground phases are appended around it.
    route = [_route_waypoint(nodes[index]) for index in path_indices]

    if start_position:
        # In-flight replan: resume from the aircraft's current airborne
        # position instead of departing from the ground again.
        resume_waypoint = _route_waypoint(start, search_start["lat"], search_start["lon"])
        resume_waypoint.update(
            {
                "y": start_position.get("y", resume_waypoint["y"]),
                "altitude_km": start_position.get("altitude_km", resume_waypoint["altitude_km"]),
                "pressure_level": start_position.get("pressure_level", start.pressure_level),
                "phase": "cruise",
            }
        )
        route = [resume_waypoint] + route
        route = extend_with_flight_phases(
            route, origin, destination, profile, grid_points,
            include_takeoff=False, include_landing=True,
        )
    else:
        route = extend_with_flight_phases(
            route, origin, destination, profile, grid_points,
            include_takeoff=True, include_landing=True,
        )

    return annotate_route(route, profile)


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def compute_route_metrics(waypoints, profile=None):
    """
    Route comparison metrics over the FULL flight (ground to ground).
    Fuel is a transparent linear model with a planned reserve — clearly a
    simulation assumption, not aircraft performance data.
    """
    profile = profile or AircraftProfile()

    def altitude(waypoint):
        value = waypoint.get("altitude_km")
        if value is not None:
            return float(value)
        return waypoint["y"] / VERTICAL_EXAGGERATION

    total_distance_km = 0.0
    total_time_min = 0.0
    climb_min = 0.0
    descent_min = 0.0
    altitude_changes = 0
    for start, end in zip(waypoints, waypoints[1:]):
        start_altitude, end_altitude = altitude(start), altitude(end)
        distance_km = math.sqrt(
            (end["x"] - start["x"]) ** 2
            + (end["z"] - start["z"]) ** 2
            + (end_altitude - start_altitude) ** 2
        )
        total_distance_km += distance_km

        edge_time = edge_travel_time_min(
            {"x": start["x"], "z": start["z"], "altitude_km": start_altitude},
            {"x": end["x"], "z": end["z"], "altitude_km": end_altitude},
            profile,
        )
        total_time_min += edge_time
        if end.get("phase") == "takeoff":
            climb_min += edge_time
        elif end.get("phase") == "landing":
            descent_min += edge_time

        if (start.get("pressure_level") is not None
                and end.get("pressure_level") is not None
                and start.get("pressure_level") != end.get("pressure_level")):
            altitude_changes += 1

    fuel_burn_kg = profile.effective_fuel_burn_kg_per_hour * total_time_min / 60
    initial_fuel_kg = min(
        profile.fuel_capacity_kg,
        fuel_burn_kg * (1 + FUEL_RESERVE_FRACTION),
    )
    fuel_remaining_kg = initial_fuel_kg - fuel_burn_kg

    exposures = [
        waypoint["exposure_score"]
        for waypoint in waypoints
        if waypoint.get("exposure_score") is not None
    ]
    metrics = {
        "distance_km": round(total_distance_km, 1),
        "time_min": round(total_time_min, 1),
        "avg_exposure": round(sum(exposures) / len(exposures), 1) if exposures else None,
        "altitude_changes": altitude_changes,
        "climb_min": round(climb_min, 1),
        "descent_min": round(descent_min, 1),
        "fuel_estimated_kg": round(fuel_burn_kg, 1),
        "initial_fuel_kg": round(initial_fuel_kg, 1),
        "fuel_remaining_kg": round(fuel_remaining_kg, 1),
        "fuel_reserve_fraction": FUEL_RESERVE_FRACTION,
    }
    if fuel_burn_kg * (1 + FUEL_RESERVE_FRACTION) > profile.fuel_capacity_kg:
        metrics["fuel_status"] = "exceeds_capacity"
    elif fuel_remaining_kg < 0:
        metrics["fuel_status"] = "insufficient_fuel"
    return metrics


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