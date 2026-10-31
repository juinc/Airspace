import math

import pytest

from grid.coordinates import (
    FALLBACK_ALTITUDE_M,
    altitude_to_scene_y,
    latlon_to_scene_xz,
)
from optimizer.astar import (
    WEATHER_WEIGHTS,
    _build_nodes,
    _neighbors,
    calculate_edge_cost,
    compute_route_metrics,
    find_path,
    normalize_mode,
)


def _grid(rows=3, columns=5, levels=(250,), high_exposure_cells=()):
    points = []
    high_exposure_cells = set(high_exposure_cells)
    for row in range(rows):
        lat = 44.0 + row * 0.1
        for column in range(columns):
            lon = 23.0 + column * 0.1
            x, z = latlon_to_scene_xz(lat, lon)
            point = {"lat": lat, "lon": lon, "x": x, "z": z, "levels": {}}
            for level in levels:
                altitude_m = FALLBACK_ALTITUDE_M[level]
                score = 100 if (row, column) in high_exposure_cells else 0
                point["levels"][level] = {
                    "altitude_km": altitude_m / 1000,
                    "y": altitude_to_scene_y(altitude_m),
                    "exposure_score": score,
                }
            points.append(point)
    return points


def test_edge_cost_applies_destination_weather_and_altitude_penalty():
    current = {
        "x": 0,
        "z": 0,
        "altitude_km": 10,
        "pressure_level": 250,
    }
    destination = {
        "x": 3,
        "z": 0,
        "altitude_km": 14,
        "pressure_level": 200,
        "exposure_score": 50,
    }

    expected = math.sqrt(3**2 + 4**2) / 800 * 60 * 2 + 2
    assert calculate_edge_cost(current, destination, weather_weight=2) == expected


def test_edge_cost_ignores_missing_exposure_instead_of_treating_it_as_zero_risk():
    current = {"x": 0, "z": 0, "altitude_km": 10, "pressure_level": 250}
    destination = {
        "x": 4,
        "z": 0,
        "altitude_km": 10,
        "pressure_level": 250,
        "exposure_score": None,
    }

    assert calculate_edge_cost(current, destination, weather_weight=5) == 4 / 800 * 60


def test_neighbors_include_all_26_adjacent_nodes():
    nodes, _, _, _ = _build_nodes(
        _grid(rows=3, columns=3, levels=(400, 300, 250))
    )

    assert len(list(_neighbors((1, 1, 1), nodes))) == 26
    assert len(list(_neighbors((1, 1, 0), nodes))) == 17


def test_path_detours_around_high_exposure_cells():
    grid = _grid(high_exposure_cells={(1, 1), (1, 2), (1, 3)})
    origin = {"lat": 44.1, "lon": 23.0}
    destination = {"lat": 44.1, "lon": 23.4}

    route = find_path(grid, origin, destination, mode="Balanced")

    grid_waypoints = route[1:-1]
    assert route[0]["lat"] == origin["lat"]
    assert route[-1]["lon"] == destination["lon"]
    assert not any(
        waypoint["lat"] == 44.1 and waypoint["lon"] in {23.1, 23.2, 23.3}
        for waypoint in grid_waypoints
    )


def test_weather_weight_changes_whether_a_single_high_exposure_cell_is_avoided():
    grid = _grid(
        high_exposure_cells={(1, 2)},
    )
    origin = {"lat": 44.1, "lon": 23.0}
    destination = {"lat": 44.1, "lon": 23.4}

    fastest = find_path(grid, origin, destination, mode="Fastest")
    lower_exposure = find_path(grid, origin, destination, mode="Lower-exposure")
    risky_cell = (44.1, 23.2)

    assert any((waypoint["lat"], waypoint["lon"]) == risky_cell for waypoint in fastest)
    assert not any(
        (waypoint["lat"], waypoint["lon"]) == risky_cell for waypoint in lower_exposure
    )


def test_path_supports_missing_exposure_and_preference_mode_weights():
    grid = _grid(rows=2, columns=2)
    grid[1]["levels"][250]["exposure_score"] = None

    route = find_path(grid, {"lat": 44, "lon": 23}, {"lat": 44.1, "lon": 23.1})

    assert len(route) >= 2
    assert normalize_mode("Lower-exposure") == "lower-exposure"
    assert WEATHER_WEIGHTS == {
        "fastest": 0.5,
        "balanced": 2.0,
        "lower-exposure": 5.0,
    }
    with pytest.raises(ValueError, match="mode must be"):
        find_path(grid, {"lat": 44, "lon": 23}, {"lat": 44.1, "lon": 23.1}, "unknown")


def test_route_metrics_measure_physical_vertical_distance_and_skip_null_exposure():
    route = [
        {"x": 0, "y": 80, "z": 0, "exposure_score": 20},
        {"x": 3, "y": 160, "z": 4, "exposure_score": None},
    ]

    metrics = compute_route_metrics(route)
    distance_km = math.sqrt(3**2 + 4**2 + 10**2)

    assert metrics == {
        "distance_km": round(distance_km, 1),
        "time_min": round(distance_km / 800 * 60, 1),
        "avg_exposure": 20.0,
    }
