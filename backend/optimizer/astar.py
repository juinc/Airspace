import heapq
import math
import statistics
from bisect import bisect_left
from dataclasses import dataclass, asdict
from itertools import count
from typing import Optional

from grid.coordinates import (
    latlon_to_scene_xz,
    altitude_to_scene_y,
    resolve_altitude_m,
    VERTICAL_EXAGGERATION,
)

# Original Citation CJ3 nominal reference data. Published limits vary by
# serial number and installed options; modeled estimates are identified below.
AIRCRAFT_NAME = "Cessna Citation CJ3"
AIRCRAFT_VARIANT = "CJ3 (original)"
MAX_RAMP_WEIGHT_KG = 6350.3
MAX_TAKEOFF_WEIGHT_KG = 6291.4
MAX_LANDING_WEIGHT_KG = 5783.3
MAX_FUEL_CAPACITY_KG = 2136.4
MAX_CRUISE_SPEED_KTS = 416.0
MAX_RANGE_NM = 2040.0
SERVICE_CEILING_FT = 45000

# Fuel flow, descent rate, and scenario gross mass are estimates, not POH or
# dispatch-performance values.
CRUISE_SPEED_KMH = MAX_CRUISE_SPEED_KTS * 1.852
CLIMB_RATE_M_PER_MIN = 1189.0
DESCENT_RATE_M_PER_MIN = 600
ALTITUDE_CHANGE_PENALTY_MIN = 0.5
REFERENCE_WEIGHT_KG = MAX_TAKEOFF_WEIGHT_KG
FUEL_BURN_KG_PER_HOUR = 520.0
FUEL_CAPACITY_KG = MAX_FUEL_CAPACITY_KG
MAX_ALTITUDE_KM = SERVICE_CEILING_FT * 0.0003048
FUEL_RESERVE_FRACTION = 0.25

BASELINE_PRESSURE_LEVEL = 250
WEATHER_WEIGHTS = {
    "fastest": 0.5,
    "balanced": 2.0,
    "lower-exposure": 5.0,
}

# Used only when a pressure level has no usable altitude data anywhere in
# the grid — standard ISA altitudes, in meters.
FALLBACK_ALTITUDE_M = {
    500: 5890.0,
    400: 7180.0,
    300: 9160.0,
    250: 10350.0,
    200: 11780.0,
}

# ---------------------------------------------------------------------------
# Vertical profile geometry — ONE continuous, densely-sampled shape.
# ---------------------------------------------------------------------------
CLIMB_GRADIENT_KM_PER_KM = 14.0    # horizontal km flown per km of altitude gained
DESCENT_GRADIENT_KM_PER_KM = 16.0  # descents glide farther than climbs
CLIMB_DISTANCE_CAP = 0.40          # climb may use at most 40% of the route
DESCENT_DISTANCE_CAP = 0.40        # >= 20% of the route is guaranteed cruise
SAMPLE_SPACING_KM = 8.0            # dense resampling -> smooth rendered curve
GROUND_ROLL_KM = 1.5               # flat runway roll before rotation
PHASE_EASE_FRACTION = 0.20         # 20% ease in/out, 60% constant-rate
MERGE_TOLERANCE_KM = 0.4


@dataclass(frozen=True)
class AircraftProfile:
    """CJ3 reference profile with explicitly modeled flight assumptions."""

    aircraft_name: str = AIRCRAFT_NAME
    aircraft_variant: str = AIRCRAFT_VARIANT
    max_ramp_weight_kg: float = MAX_RAMP_WEIGHT_KG
    max_takeoff_weight_kg: float = MAX_TAKEOFF_WEIGHT_KG
    max_landing_weight_kg: float = MAX_LANDING_WEIGHT_KG
    max_cruise_speed_kts: float = MAX_CRUISE_SPEED_KTS
    max_range_nm: float = MAX_RANGE_NM
    service_ceiling_ft: int = SERVICE_CEILING_FT
    cruise_speed_kmh: float = CRUISE_SPEED_KMH
    climb_rate_m_per_min: float = CLIMB_RATE_M_PER_MIN
    descent_rate_m_per_min: float = DESCENT_RATE_M_PER_MIN
    altitude_change_penalty_min: float = ALTITUDE_CHANGE_PENALTY_MIN
    weight_kg: float = REFERENCE_WEIGHT_KG
    reference_weight_kg: float = REFERENCE_WEIGHT_KG
    fuel_burn_kg_per_hour: float = FUEL_BURN_KG_PER_HOUR
    fuel_capacity_kg: float = FUEL_CAPACITY_KG
    max_altitude_km: float = MAX_ALTITUDE_KM
    modeled_mass_basis: str = "Maximum takeoff mass used as the scenario gross-mass assumption"
    fuel_burn_basis: str = "520 kg/h scenario estimate; not POH or dispatch data"

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
        return self.fuel_burn_kg_per_hour * min(
            2.0, max(0.5, self.weight_kg / self.reference_weight_kg)
        )

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

def _precompute_avoid_index(routes, cell_size_km=20.0):
    """Spatial bucket grid over reserved route segments.

    AGGRESSIVE: the old check compared EVERY A* edge against EVERY segment of
    EVERY reserved route in pure Python — tens of seconds for a 3-flight
    scenario (the 'stuck on loading' cause). This buckets segments by 2D
    cell once, so each edge only tests the handful of nearby segments.
    Waypoint tuples are (x, altitude_km, z).
    """
    cells = {}
    for route in routes:
        for start, end in _route_segments(route):
            min_x, max_x = min(start[0], end[0]), max(start[0], end[0])
            min_z, max_z = min(start[2], end[2]), max(start[2], end[2])
            min_a, max_a = min(start[1], end[1]), max(start[1], end[1])
            segment = (start, end, min_x, max_x, min_z, max_z, min_a, max_a)
            for cx in range(math.floor(min_x / cell_size_km), math.floor(max_x / cell_size_km) + 1):
                for cz in range(math.floor(min_z / cell_size_km), math.floor(max_z / cell_size_km) + 1):
                    cells.setdefault((cx, cz), []).append(segment)
    return cells, cell_size_km


def _edge_intersects_routes(current, neighbor, avoid_index):
    """Edge vs reserved routes, using the precomputed bucket grid.

    The per-segment 3D bbox overlap test is a valid prefilter (a bbox always
    contains its segment), so the expensive exact distance only runs when the
    edge is genuinely near a reserved route.
    """
    cells, cell_size = avoid_index
    if not cells:
        return False
    start = (current.x, current.altitude_km, current.z)
    end = (neighbor.x, neighbor.altitude_km, neighbor.z)
    clearance_squared = ROUTE_INTERSECTION_CLEARANCE_KM ** 2

    min_x, max_x = min(start[0], end[0]), max(start[0], end[0])
    min_z, max_z = min(start[2], end[2]), max(start[2], end[2])
    min_a, max_a = min(start[1], end[1]), max(start[1], end[1])

    candidates = {}
    for cx in range(math.floor(min_x / cell_size), math.floor(max_x / cell_size) + 1):
        for cz in range(math.floor(min_z / cell_size), math.floor(max_z / cell_size) + 1):
            for segment in cells.get((cx, cz), ()):
                candidates[id(segment)] = segment

    for segment in candidates.values():
        seg_start, seg_end, sx0, sx1, sz0, sz1, sa0, sa1 = segment
        if (max_x < sx0 or min_x > sx1 or max_z < sz0 or min_z > sz1
                or max_a < sa0 or min_a > sa1):
            continue  # bbox miss — skip the expensive exact test
        if _segment_distance_squared(start, end, seg_start, seg_end) <= clearance_squared:
            return True
    return False

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


ROUTE_INTERSECTION_CLEARANCE_KM = 0.05


def _waypoint_3d(waypoint):
    altitude = waypoint.get("altitude_km")
    if altitude is None:
        altitude = waypoint["y"] / VERTICAL_EXAGGERATION
    return waypoint["x"], float(altitude), waypoint["z"]


def _segment_distance_squared(first_start, first_end, second_start, second_end):
    """Minimum squared distance between two finite 3D line segments."""
    first = tuple(end - start for start, end in zip(first_start, first_end))
    second = tuple(end - start for start, end in zip(second_start, second_end))
    offset = tuple(a - b for a, b in zip(first_start, second_start))
    dot = lambda a, b: sum(x * y for x, y in zip(a, b))
    a, b, c = dot(first, first), dot(first, second), dot(second, second)
    d, e = dot(first, offset), dot(second, offset)
    denominator = a * c - b * b

    if a <= 1e-12 and c <= 1e-12:
        return dot(offset, offset)
    if a <= 1e-12:
        first_fraction = 0.0
        second_fraction = min(1.0, max(0.0, e / c))
    elif c <= 1e-12:
        second_fraction = 0.0
        first_fraction = min(1.0, max(0.0, -d / a))
    else:
        first_fraction = 0.0 if denominator <= 1e-12 else min(
            1.0, max(0.0, (b * e - c * d) / denominator)
        )
        second_fraction = (b * first_fraction + e) / c
        if second_fraction < 0.0:
            second_fraction = 0.0
            first_fraction = min(1.0, max(0.0, -d / a))
        elif second_fraction > 1.0:
            second_fraction = 1.0
            first_fraction = min(1.0, max(0.0, (b - d) / a))

    separation = tuple(
        delta + first_fraction * first_axis - second_fraction * second_axis
        for delta, first_axis, second_axis in zip(offset, first, second)
    )
    return dot(separation, separation)


def _route_segments(route):
    for start, end in zip(route, route[1:]):
        if start.get("phase") in {"takeoff", "landing"}:
            continue
        if end.get("phase") in {"takeoff", "landing"}:
            continue
        yield _waypoint_3d(start), _waypoint_3d(end)


def routes_intersect(first_route, second_route,
                     clearance_km=ROUTE_INTERSECTION_CLEARANCE_KM):
    """Whether two routes cross or pass within the configured 3D clearance.

    Takeoff and landing segments are excluded because multiple routes may
    legitimately share airport terminal points in these demonstration scenes.
    """
    minimum_distance_squared = clearance_km * clearance_km
    second_segments = tuple(_route_segments(second_route))
    return any(
        _segment_distance_squared(start, end, other_start, other_end)
        <= minimum_distance_squared
        for start, end in _route_segments(first_route)
        for other_start, other_end in second_segments
    )


def _edge_intersects_routes(current, neighbor, avoid_index):
    """Edge vs reserved routes, using the precomputed bucket grid.

    The per-segment 3D bbox overlap test is a valid prefilter (a bbox always
    contains its segment), so the expensive exact distance only runs when the
    edge is genuinely near a reserved route.
    """
    cells, cell_size = avoid_index
    if not cells:
        return False
    start = (current.x, current.altitude_km, current.z)
    end = (neighbor.x, neighbor.altitude_km, neighbor.z)
    clearance_squared = ROUTE_INTERSECTION_CLEARANCE_KM ** 2

    min_x, max_x = min(start[0], end[0]), max(start[0], end[0])
    min_z, max_z = min(start[2], end[2]), max(start[2], end[2])
    min_a, max_a = min(start[1], end[1]), max(start[1], end[1])

    candidates = {}
    for cx in range(math.floor(min_x / cell_size), math.floor(max_x / cell_size) + 1):
        for cz in range(math.floor(min_z / cell_size), math.floor(max_z / cell_size) + 1):
            for segment in cells.get((cx, cz), ()):
                candidates[id(segment)] = segment

    for segment in candidates.values():
        seg_start, seg_end, sx0, sx1, sz0, sz1, sa0, sa1 = segment
        if (max_x < sx0 or min_x > sx1 or max_z < sz0 or min_z > sz1
                or max_a < sa0 or min_a > sa1):
            continue  # bbox miss — skip the expensive exact test
        if _segment_distance_squared(start, end, seg_start, seg_end) <= clearance_squared:
            return True
    return False


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
# Spatial index for nearest-cell lookups
# ---------------------------------------------------------------------------

class _BucketIndex:
    """
    Uniform x/z bucket grid for fast nearest-entry queries.

    Replaces the previous full O(n) scan per query. With ~900 grid points
    and ~100 route waypoints per request, that was ~500k+ distance
    computations per scene build — now each query touches only its own
    bucket and the immediate neighbors.
    """

    def __init__(self, entries, bucket_size):
        # entries: iterable of (x, z, payload)
        self.bucket_size = max(float(bucket_size), 1e-6)
        self.buckets = {}
        for x, z, payload in entries:
            key = self._key(x, z)
            if key not in self.buckets:
                self.buckets[key] = []
            self.buckets[key].append((x, z, payload))

    def _key(self, x, z):
        return (math.floor(x / self.bucket_size), math.floor(z / self.bucket_size))

    def nearest(self, x, z):
        """Return the payload of the nearest entry, or None when empty."""
        if not self.buckets:
            return None
        bx, bz = self._key(x, z)
        # Expand the search ring until we find any entry, then scan one ring
        # beyond to guarantee correctness across bucket boundaries.
        for radius in range(0, 64):
            if not self._ring_has_entries(bx, bz, radius):
                continue
            search_radius = radius + 1
            best_payload = None
            best_distance = float("inf")
            for cx in range(bx - search_radius, bx + search_radius + 1):
                for cz in range(bz - search_radius, bz + search_radius + 1):
                    for entry_x, entry_z, payload in self.buckets.get((cx, cz), ()):
                        distance = (entry_x - x) ** 2 + (entry_z - z) ** 2
                        if distance < best_distance:
                            best_distance = distance
                            best_payload = payload
            return best_payload
        return None

    def _ring_has_entries(self, bx, bz, radius):
        if radius == 0:
            return (bx, bz) in self.buckets
        for cx in (bx - radius, bx + radius):
            for cz in range(bz - radius, bz + radius + 1):
                if (cx, cz) in self.buckets:
                    return True
        for cz in (bz - radius, bz + radius):
            for cx in range(bx - radius + 1, bx + radius):
                if (cx, cz) in self.buckets:
                    return True
        return False


def _bucket_size_for(entries):
    """One bucket per ~sqrt(n) divisions of the span — balanced occupancy."""
    xs = [x for x, _, _ in entries]
    zs = [z for _, z, _ in entries]
    span_x = max(xs) - min(xs) if xs else 1.0
    span_z = max(zs) - min(zs) if zs else 1.0
    return max(span_x, span_z) / max(1, int(math.sqrt(len(entries))))


# ---------------------------------------------------------------------------
# Exposure lookup for phase waypoints
# ---------------------------------------------------------------------------

def _surface_exposure_lookup(grid_points):
    """Nearest-cell exposure samples for climb/descent waypoints.

    AIFS provides no data below the lowest pressure level, so phase
    waypoints use the LOWEST available forecast level — the closest data
    to that altitude. Never fabricated, never zero.

    Returns a _BucketIndex (or None when the grid has nothing usable) so
    per-waypoint nearest-cell queries are near O(1) instead of O(grid).
    """
    try:
        lowest_level = _pressure_levels(grid_points)[0]
    except (ValueError, TypeError, IndexError):
        return None
    entries = []
    for point in grid_points:
        data = _level_data(point, lowest_level)
        if not data:
            continue
        x, z = point.get("x"), point.get("z")
        if x is None or z is None:
            x, z = latlon_to_scene_xz(point["lat"], point["lon"])
        entries.append((float(x), float(z), data.get("exposure_score")))

    if not entries:
        return None
    return _BucketIndex(entries, _bucket_size_for(entries))


def _nearest_surface_exposure(lookup, x, z):
    if lookup is None:
        return None
    return lookup.nearest(x, z)


# ---------------------------------------------------------------------------
# Continuous vertical profile
# ---------------------------------------------------------------------------

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
        "exposure_score": exposure,
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
            "x": node["x"], "z": node["z"], "altitude_km": node.get("altitude_km") or 0.0,
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
    """Linear interpolation of (lat, lon, x, z, altitude_km) at distance s.

    Binary search over the cumulative distances — the previous linear scan
    made route resampling O(n^2) overall (n_samples * n_segments).
    """
    if s <= 0.0:
        p = points[0]
        return p["lat"], p["lon"], p["x"], p["z"], p["altitude_km"]
    if s >= dists[-1]:
        p = points[-1]
        return p["lat"], p["lon"], p["x"], p["z"], p["altitude_km"]

    i = bisect_left(dists, s) - 1
    if i < 0:
        i = 0
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

    if include_takeoff:
        points = _polyline_points(route, origin, destination)
    else:
        points = [
            {
                "lat": waypoint["lat"],
                "lon": waypoint["lon"],
                "x": waypoint["x"],
                "z": waypoint["z"],
                "altitude_km": waypoint.get("altitude_km") or 0.0,
            }
            for waypoint in route
        ]
        destination_x, destination_z = latlon_to_scene_xz(
            destination["lat"], destination["lon"]
        )
        points.append(
            {
                "lat": destination["lat"],
                "lon": destination["lon"],
                "x": destination_x,
                "z": destination_z,
                "altitude_km": 0.0,
            }
        )
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
        return max(0.0, alt)

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
        if node.get("exposure_score") is None:
            node["exposure_score"] = _nearest_surface_exposure(lookup, x, z)
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
    Fills in display/metadata fields on an already-computed route.
    grid_points must be the weather grid (a list of dicts) or None —
    anything else (e.g. an AircraftProfile passed by mistake) is ignored.
    Mutates and returns the route.
    """
    if isinstance(grid_points, list) and grid_points and isinstance(grid_points[0], dict):
        lookup = _surface_exposure_lookup(grid_points)
    else:
        lookup = None

    for waypoint in route:
        if waypoint.get("exposure_score") is None:
            waypoint["exposure_score"] = (
                _nearest_surface_exposure(lookup, waypoint["x"], waypoint["z"])
                if lookup else 0
            )
        if waypoint.get("phase") is None:
            waypoint["phase"] = default_phase
        waypoint.setdefault("pressure_level", None)
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


class _ExposureIndex:
    """
    Bucketed nearest-cell exposure lookup, keyed per pressure level.

    Handles both int and str level keys (JSON round-trips through the
    frontend turn int keys into strings). Built once per grid; each
    waypoint query then touches only its own bucket and neighbors.
    """

    def __init__(self, grid):
        self.by_level = {}
        if not grid:
            return
        entries_by_level = {}
        for point in grid:
            levels = point.get("levels", {})
            x, z = point.get("x"), point.get("z")
            if x is None or z is None:
                x, z = latlon_to_scene_xz(point["lat"], point["lon"])
            x, z = float(x), float(z)
            for level, level_data in levels.items():
                if not level_data:
                    continue
                entries_by_level.setdefault(level, []).append(
                    (x, z, level_data.get("exposure_score"))
                )
        for level, entries in entries_by_level.items():
            self.by_level[level] = _BucketIndex(entries, _bucket_size_for(entries))

    def nearest_exposure(self, waypoint, pressure_level):
        if pressure_level is None:
            return None
        index = self.by_level.get(pressure_level) or self.by_level.get(str(pressure_level))
        if index is None:
            return None
        return index.nearest(float(waypoint["x"]), float(waypoint["z"]))


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

    # Build both spatial indexes ONCE for the whole assessment instead of
    # scanning the full grid per waypoint.
    previous_index = _ExposureIndex(previous_grid) if previous_grid else None
    updated_index = _ExposureIndex(updated_grid) if updated_grid else None

    changes = []
    for waypoint in samples:
        pressure_level = waypoint.get("pressure_level")
        previous_score = (
            previous_index.nearest_exposure(waypoint, pressure_level)
            if previous_index else None
        )
        updated_score = (
            updated_index.nearest_exposure(waypoint, pressure_level)
            if updated_index else None
        )
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


# Kept for backwards compatibility with any external callers.
def _nearest_exposure(grid, waypoint, pressure_level):
    if pressure_level is None or not grid:
        return None
    return _ExposureIndex(grid).nearest_exposure(waypoint, pressure_level)


# ---------------------------------------------------------------------------
# A* search
# ---------------------------------------------------------------------------

def find_path(grid_points, origin, destination, mode="Balanced",
              start_position=None, profile=None, avoid_routes=None):
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
    avoid_routes = avoid_routes or ()
    avoid_index = _precompute_avoid_index(avoid_routes) if avoid_routes else None

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
            if avoid_index and _edge_intersects_routes(current, neighbor, avoid_index):
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

    # Cruise path: grid nodes only. The ground phases are wrapped around it.
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

    return annotate_route(route, grid_points)


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
    """Return high-exposure baseline cells absent from the optimized path.

    Uses a bucketed spatial index per pressure level, built once, instead
    of scanning every node per waypoint — this was the single largest CPU
    sink in the scene payload build after A* itself.
    """
    nodes, _, _, _ = _build_nodes(grid_points)
    baseline_level = BASELINE_PRESSURE_LEVEL

    index_by_level = {}
    all_levels = {node.pressure_level for node in nodes.values()}
    for level in all_levels:
        entries = [
            (node.x, node.z, node)
            for node in nodes.values()
            if node.pressure_level == level
        ]
        if entries:
            index_by_level[level] = _BucketIndex(entries, _bucket_size_for(entries))

    def nearest_node_at(waypoint, pressure_level=None):
        if pressure_level is not None:
            index = index_by_level.get(pressure_level)
            if index is None:
                return None
            return index.nearest(float(waypoint["x"]), float(waypoint["z"]))
        # Any level: nearest across levels by 3D distance (matches the
        # original _nearest_grid_cell semantics).
        best = None
        best_distance = float("inf")
        for index in index_by_level.values():
            payload = index.nearest(float(waypoint["x"]), float(waypoint["z"]))
            if payload is None:
                continue
            distance = (
                (payload.x - waypoint["x"]) ** 2
                + (payload.z - waypoint["z"]) ** 2
                + ((payload.y - waypoint["y"]) / VERTICAL_EXAGGERATION) ** 2
            )
            if distance < best_distance:
                best_distance = distance
                best = payload
        return best

    optimized_cells = set()
    for waypoint in optimized_route:
        matching = nearest_node_at(waypoint)
        if matching is not None:
            optimized_cells.add(
                (matching.lat, matching.lon, matching.pressure_level)
            )

    avoided = {}
    for waypoint in baseline_route:
        matching = nearest_node_at(waypoint, baseline_level)
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