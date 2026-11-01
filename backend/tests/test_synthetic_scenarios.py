import heapq
from itertools import count

import pytest
from fastapi.testclient import TestClient

import main
from main import DEFAULT_CONFIG, ROUTE
from optimizer.astar import (
    WEATHER_WEIGHTS,
    _build_nodes,
    _nearest_node,
    _neighbors,
    calculate_edge_cost,
    routes_intersect,
)
from synthetic_scenarios import (
    MULTI_FLIGHT_SCENARIOS,
    SYNTHETIC_CONFIG,
    build_multi_flight_routes,
    build_synthetic_events,
    build_synthetic_grid,
    build_synthetic_routes,
)

client = TestClient(main.app)


def _build_scene(scenario):
    grid = build_synthetic_grid(scenario, DEFAULT_CONFIG)
    return grid, build_synthetic_events(grid), build_synthetic_routes(grid, ROUTE)


def _dijkstra_cost(grid, mode):
    nodes, _, _, _ = _build_nodes(grid)
    start = _nearest_node(nodes, ROUTE["origin"], preferred_layer=0)
    goal = _nearest_node(nodes, ROUTE["destination"], preferred_layer=0)
    tie_breaker = count()
    queue = [(0.0, next(tie_breaker), start.index)]
    costs = {start.index: 0.0}

    while queue:
        cost, _, index = heapq.heappop(queue)
        if index == goal.index:
            return cost
        if cost != costs[index]:
            continue
        current = nodes[index]
        for neighbor in _neighbors(index, nodes):
            candidate = cost + calculate_edge_cost(
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
                WEATHER_WEIGHTS[mode],
            )
            if candidate < costs.get(neighbor.index, float("inf")):
                costs[neighbor.index] = candidate
                heapq.heappush(
                    queue, (candidate, next(tie_breaker), neighbor.index)
                )
    raise AssertionError("Dijkstra could not connect the country-wide test grid")


def test_random_storm_scenario_finds_route_across_full_country_grid():
    grid, events, routes = _build_scene("random-storms")
    nodes, _, _, _ = _build_nodes(grid)
    path_nodes = {
        (node.lat, node.lon, node.y): node for node in nodes.values()
    }
    grid_route = [
        path_nodes[(point["lat"], point["lon"], point["y"])]
        for point in routes["optimized"][1:-1]
    ]
    astar_cost = sum(
        calculate_edge_cost(
            {
                "x": start.x,
                "z": start.z,
                "altitude_km": start.altitude_km,
                "pressure_level": start.pressure_level,
            },
            {
                "x": end.x,
                "z": end.z,
                "altitude_km": end.altitude_km,
                "pressure_level": end.pressure_level,
                "exposure_score": end.exposure_score,
            },
            WEATHER_WEIGHTS["balanced"],
        )
        for start, end in zip(grid_route, grid_route[1:])
    )

    assert len(grid) == 288
    assert all(len(point["levels"]) == 4 for point in grid)
    assert len(_build_nodes(grid)[0]) == 1152
    assert all(
        not {"cape", "precipitation", "cloud_cover"}.intersection(level)
        for point in grid
        for level in point["levels"].values()
    )
    assert all(point["forecast_time"] for point in grid)
    assert {event["type"] for event in events} == {
        "rain",
        "thunderstorm",
        "severe_storm",
    }
    assert routes["optimized"][0]["lat"] == ROUTE["origin"]["lat"]
    assert routes["optimized"][-1]["lon"] == ROUTE["destination"]["lon"]
    assert len(routes["optimized"]) >= 3
    assert routes["metrics"]["optimized"]["distance_km"] > 0
    assert astar_cost == pytest.approx(_dijkstra_cost(grid, "balanced"))


def test_heavy_storm_scenario_generates_much_more_weather_than_random():
    _, random_events, _ = _build_scene("random-storms")
    grid, heavy_events, routes = _build_scene("heavy-storms")
    random_affected_cells = sum(event["cell_count"] for event in random_events)
    heavy_affected_cells = sum(event["cell_count"] for event in heavy_events)

    assert len(grid) == 288
    assert heavy_affected_cells > random_affected_cells * 2
    assert heavy_affected_cells > len(grid) * 2
    assert len(routes["optimized"]) >= 3


def test_clear_airspace_scenario_has_no_weather_events_and_still_routes():
    grid, events, routes = _build_scene("clear-airspace")

    assert len(grid) == 288
    assert events == []
    assert all(
        level["exposure_score"] == 0
        for point in grid
        for level in point["levels"].values()
    )
    assert len(routes["optimized"]) >= 3


@pytest.mark.parametrize("scenario", MULTI_FLIGHT_SCENARIOS)
def test_multi_flight_scenario_routes_do_not_intersect_enroute(scenario):
    grid = build_synthetic_grid(scenario, SYNTHETIC_CONFIG)
    flights = build_multi_flight_routes(
        grid, MULTI_FLIGHT_SCENARIOS[scenario]["flights"]
    )

    for index, flight in enumerate(flights):
        for other in flights[index + 1:]:
            assert not routes_intersect(flight["optimized"], other["optimized"])


def test_layered_random_weather_varies_by_level_and_astar_uses_vertical_path():
    grid = build_synthetic_grid("layered-random", DEFAULT_CONFIG)
    routes = build_synthetic_routes(grid, ROUTE)

    assert all(
        not {"cape", "precipitation", "cloud_cover"}.intersection(level)
        for point in grid
        for level in point["levels"].values()
    )
    assert any(
        len({level["exposure_score"] for level in point["levels"].values()}) > 1
        for point in grid
    )
    assert len({waypoint["y"] for waypoint in routes["optimized"]}) > 1


def test_baseline_is_straight_at_default_pressure_and_matches_optimized_count():
    grid = build_synthetic_grid("random-storms", DEFAULT_CONFIG)
    routes = build_synthetic_routes(grid, ROUTE)
    baseline = routes["baseline"]

    assert len(baseline) == len(routes["optimized"])
    assert all(point["pressure_level"] == 250 for point in baseline)
    for index, point in enumerate(baseline):
        fraction = index / (len(baseline) - 1)
        assert point["lat"] == pytest.approx(
            ROUTE["origin"]["lat"]
            + (ROUTE["destination"]["lat"] - ROUTE["origin"]["lat"]) * fraction,
            abs=1e-5,
        )
        assert point["lon"] == pytest.approx(
            ROUTE["origin"]["lon"]
            + (ROUTE["destination"]["lon"] - ROUTE["origin"]["lon"]) * fraction,
            abs=1e-5,
        )


def test_heavy_storm_scenario_endpoint_returns_json_without_live_weather(monkeypatch):
    monkeypatch.setattr(
        main,
        "fetch_forecast",
        lambda *args, **kwargs: pytest.fail("Synthetic scenarios must not call weather API"),
    )

    response = client.get("/test-scenarios/heavy-storms")

    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["scenario"] == "heavy-storms"
    assert len(payload["grid"]) == 288
    assert sum(event["cell_count"] for event in payload["events"]) > len(payload["grid"]) * 2
    assert payload["routes"]["optimized"]


def test_synthetic_scenario_endpoint_rejects_unknown_scenario():
    response = client.get("/test-scenarios/tornadoes")

    assert response.status_code == 400
    assert response.json()["detail"] == "Unknown scenario: tornadoes"


def test_drastic_weather_scenario_replans_from_current_route_progress():
    response = client.get(
        "/test-scenarios/drastic-weather-change?route_progress=0.4"
    )

    assert response.status_code == 200
    payload = response.json()
    update = payload["weather_update"]
    assert update["drastic"] is True
    assert update["replanned"] is True
    assert update["route_progress"] == 0.4
    assert update["affected_waypoint_count"] > 0
    assert payload["routes"]["previous_optimized"]
    assert payload["routes"]["optimized"][0]["lat"] == pytest.approx(
        update["resume_position"]["lat"]
    )
    assert payload["routes"]["optimized"][0]["lon"] == pytest.approx(
        update["resume_position"]["lon"]
    )
    assert payload["meta"]["trajectory_status"].startswith("A* replanned")
    assert update["weather_seed"] == 0


def test_weather_seed_changes_subsequent_drastic_update():
    first = build_synthetic_grid(
        "drastic-weather-change",
        DEFAULT_CONFIG,
        weather_seed=17,
    )
    second = build_synthetic_grid(
        "drastic-weather-change",
        DEFAULT_CONFIG,
        weather_seed=29,
    )

    assert any(
        first_point["levels"][level]["exposure_score"]
        != second_point["levels"][level]["exposure_score"]
        for first_point, second_point in zip(first, second)
        for level in main.PRESSURE_LEVELS
    )
    changed_weather_types = sum(
        _synthetic_weather_type(first_point) != _synthetic_weather_type(second_point)
        for first_point, second_point in zip(first, second)
    )
    assert changed_weather_types > len(first) * 0.6


def test_drastic_weather_redraw_covers_the_entire_grid():
    grid = build_synthetic_grid(
        "drastic-weather-change",
        DEFAULT_CONFIG,
        weather_seed=71,
    )
    weather_cells = [
        point
        for point in grid
        if point["cape"] > 0 or point["precipitation"] > 0
    ]
    quadrants = {
        (point["lat"] >= 45.625, point["lon"] >= 24.875)
        for point in weather_cells
    }

    assert len(weather_cells) > len(grid) * 0.65
    assert len(weather_cells) < len(grid) * 0.85
    assert len(quadrants) == 4


def _synthetic_weather_type(point):
    if point["cape"] >= 2500:
        return "severe_storm"
    if point["cape"] >= 1000:
        return "thunderstorm"
    if point["precipitation"] >= 1:
        return "rain"
    return "clear"
