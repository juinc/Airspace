import pytest
from fastapi.testclient import TestClient

import main
from main import DEFAULT_CONFIG, ROUTE
from optimizer.astar import (
    _build_nodes,
    routes_intersect,
)
from synthetic_scenarios import (
    MULTI_FLIGHT_SCENARIOS,
    SYNTHETIC_CONFIG,
    build_multi_flight_routes,
    build_synthetic_events,
    build_synthetic_grid,
    build_synthetic_routes,
    spawn_route_blockage,
)

client = TestClient(main.app)


def _build_scene(scenario):
    grid = build_synthetic_grid(scenario, DEFAULT_CONFIG)
    return grid, build_synthetic_events(grid), build_synthetic_routes(grid, ROUTE)


def test_storm_wall_scenario_builds_layered_weather_and_route():
    grid, events, routes = _build_scene("storm-wall")
    nodes, _, _, _ = _build_nodes(grid)

    assert len(grid) == 136
    assert all(len(point["levels"]) == 5 for point in grid)
    assert len(nodes) == 680
    assert all(
        not {"cape", "precipitation", "cloud_cover"}.intersection(level)
        for point in grid
        for level in point["levels"].values()
    )
    assert all(point["forecast_time"] for point in grid)
    assert events
    assert "severe_storm" in {event["type"] for event in events}
    assert routes["optimized"][0]["lat"] == ROUTE["origin"]["lat"]
    assert routes["optimized"][-1]["lon"] == pytest.approx(
        ROUTE["destination"]["lon"], abs=1e-5
    )
    assert len(routes["optimized"]) >= 3
    assert routes["metrics"]["optimized"]["distance_km"] > 0


def test_vertical_scenarios_apply_weather_to_different_pressure_layers():
    over_the_top = build_synthetic_grid("over-the-top", DEFAULT_CONFIG)
    low_corridor = build_synthetic_grid("low-corridor", DEFAULT_CONFIG)

    assert any(
        point["levels"][250]["exposure_score"] == 0
        and point["levels"][300]["exposure_score"] > 0
        for point in over_the_top
    )
    assert any(
        point["levels"][300]["exposure_score"] == 0
        and point["levels"][250]["exposure_score"] > 0
        for point in low_corridor
    )


def test_clear_airspace_scenario_has_no_weather_events_and_still_routes():
    grid, events, routes = _build_scene("clear-airspace")

    assert len(grid) == 136
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


def test_over_the_top_scenario_routes_through_clearer_altitude_layers():
    grid = build_synthetic_grid("over-the-top", DEFAULT_CONFIG)
    routes = build_synthetic_routes(grid, ROUTE)

    assert any(
        waypoint["phase"] == "cruise"
        and waypoint["pressure_level"] in {250, 200}
        for waypoint in routes["optimized"]
    )


def test_baseline_is_straight_at_default_pressure_and_matches_optimized_count():
    grid = build_synthetic_grid("storm-wall", DEFAULT_CONFIG)
    routes = build_synthetic_routes(grid, ROUTE)
    baseline = routes["baseline"]

    assert len(baseline) == len(routes["optimized"])
    pressure_waypoints = [point for point in baseline if point["pressure_level"] is not None]
    assert pressure_waypoints
    assert all(
        point["pressure_level"] == 250
        for point in pressure_waypoints
    )
    cruise_points = [point for point in baseline if point["phase"] == "cruise"]
    latitude_delta = ROUTE["destination"]["lat"] - ROUTE["origin"]["lat"]
    longitude_delta = ROUTE["destination"]["lon"] - ROUTE["origin"]["lon"]
    assert all(
        abs(
            (point["lat"] - ROUTE["origin"]["lat"]) * longitude_delta
            - (point["lon"] - ROUTE["origin"]["lon"]) * latitude_delta
        ) < 1e-4
        for point in cruise_points
    )


def test_storm_wall_scenario_endpoint_returns_json_without_live_weather(monkeypatch):
    monkeypatch.setattr(
        main,
        "fetch_forecast",
        lambda *args, **kwargs: pytest.fail("Synthetic scenarios must not call weather API"),
    )

    response = client.get("/test-scenarios/storm-wall")

    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["scenario"] == "storm-wall"
    assert len(payload["grid"]) == 136
    assert payload["events"]
    assert payload["routes"]["optimized"]


def test_synthetic_scenario_endpoint_rejects_unknown_scenario():
    response = client.get("/test-scenarios/tornadoes")

    assert response.status_code == 404
    assert response.json()["detail"] == "Unknown scenario: tornadoes"


def test_in_flight_replan_scenario_replans_from_current_route_progress():
    response = client.get(
        "/test-scenarios/in-flight-replan?route_progress=0.4"
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
    assert payload["meta"]["scenario"] == "in-flight-replan"
    assert payload["meta"]["trajectory_status"].startswith("A* replanned")
    assert update["weather_seed"] == 0


def test_weather_seed_changes_spawned_route_blockage():
    previous_grid = build_synthetic_grid("clear-airspace", DEFAULT_CONFIG)
    previous_routes = build_synthetic_routes(previous_grid, ROUTE)
    original_grid = [dict(point) for point in previous_grid]

    first = spawn_route_blockage(
        previous_grid, previous_routes["optimized"], 0.3, weather_seed=17
    )
    second = spawn_route_blockage(
        previous_grid, previous_routes["optimized"], 0.3, weather_seed=29
    )

    assert previous_grid == original_grid
    assert first != second
    assert any(
        first_point["levels"][level]["exposure_score"]
        != second_point["levels"][level]["exposure_score"]
        for first_point, second_point in zip(first, second)
        for level in main.PRESSURE_LEVELS
    )


def test_spawned_blockage_is_localized_ahead_of_the_aircraft():
    previous_grid = build_synthetic_grid("clear-airspace", DEFAULT_CONFIG)
    previous_route = build_synthetic_routes(previous_grid, ROUTE)["optimized"]
    updated_grid = spawn_route_blockage(
        previous_grid, previous_route, route_progress=0.4, weather_seed=71
    )
    changed_cells = [
        point
        for previous, point in zip(previous_grid, updated_grid)
        if any(
            previous["levels"][level]["exposure_score"]
            != point["levels"][level]["exposure_score"]
            for level in main.PRESSURE_LEVELS
        )
    ]

    assert changed_cells
    assert len(changed_cells) < len(updated_grid)
    assert all(
        point["cape"] >= 2500
        for point in changed_cells
    )


def _synthetic_weather_type(point):
    if point["cape"] >= 2500:
        return "severe_storm"
    if point["cape"] >= 1000:
        return "thunderstorm"
    if point["precipitation"] >= 1:
        return "rain"
    return "clear"
