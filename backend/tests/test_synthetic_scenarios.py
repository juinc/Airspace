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
)
from synthetic_scenarios import (
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

    assert len(grid) == 861
    assert all(len(point["levels"]) == 4 for point in grid)
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

    assert len(grid) == 861
    assert len(heavy_events) > len(random_events) * 2
    assert len(heavy_events) > 500
    assert len(routes["optimized"]) >= 3


def test_clear_airspace_scenario_has_no_weather_events_and_still_routes():
    grid, events, routes = _build_scene("clear-airspace")

    assert len(grid) == 861
    assert events == []
    assert all(
        level["exposure_score"] == 0
        for point in grid
        for level in point["levels"].values()
    )
    assert len(routes["optimized"]) >= 3


def test_layered_random_weather_varies_by_level_and_astar_uses_vertical_path():
    grid = build_synthetic_grid("layered-random", DEFAULT_CONFIG)
    routes = build_synthetic_routes(grid, ROUTE)

    assert any(
        len({level["exposure_score"] for level in point["levels"].values()}) > 1
        for point in grid
    )
    assert len({waypoint["y"] for waypoint in routes["optimized"]}) > 1


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
    assert len(payload["grid"]) == 861
    assert len(payload["events"]) > 500
    assert payload["routes"]["optimized"]


def test_synthetic_scenario_endpoint_rejects_unknown_scenario():
    response = client.get("/test-scenarios/tornadoes")

    assert response.status_code == 400
    assert response.json()["detail"] == "Unknown scenario: tornadoes"
