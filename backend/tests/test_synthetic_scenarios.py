import math

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
)

client = TestClient(main.app)


def _build_scene(scenario):
    grid = build_synthetic_grid(scenario, DEFAULT_CONFIG)
    return grid, build_synthetic_events(grid), build_synthetic_routes(grid, ROUTE)


def test_random_storm_scenario_finds_route_across_masked_country_grid():
    grid, events, routes = _build_scene("random-storms")
    nodes, _, _, _ = _build_nodes(grid)

    assert len(grid) > 100
    assert all(len(point["levels"]) == len(grid[0]["levels"]) for point in grid)
    assert len(nodes) == len(grid) * len(grid[0]["levels"])
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
    assert routes["optimized"][-1]["lon"] == pytest.approx(
        ROUTE["destination"]["lon"], abs=1e-5
    )
    assert len(routes["optimized"]) >= 3
    assert routes["metrics"]["optimized"]["distance_km"] > 0
    assert all(
        math.isfinite(point["lat"])
        and math.isfinite(point["lon"])
        and (
            point["pressure_level"] is None
            or point["pressure_level"] in grid[0]["levels"]
        )
        for point in routes["optimized"]
    )


def test_heavy_storm_scenario_generates_much_more_weather_than_random():
    _, random_events, _ = _build_scene("random-storms")
    grid, heavy_events, routes = _build_scene("heavy-storms")
    random_affected_cells = sum(event["cell_count"] for event in random_events)
    heavy_affected_cells = sum(event["cell_count"] for event in heavy_events)

    assert len(grid) > 100
    assert heavy_affected_cells > random_affected_cells * 2
    assert heavy_affected_cells > len(grid) * 2
    assert len(routes["optimized"]) >= 3


def test_clear_airspace_scenario_has_no_weather_events_and_still_routes():
    grid, events, routes = _build_scene("clear-airspace")

    assert len(grid) > 100
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


def test_baseline_is_straight_and_uses_default_pressure_during_cruise():
    grid = build_synthetic_grid("random-storms", DEFAULT_CONFIG)
    routes = build_synthetic_routes(grid, ROUTE)
    baseline = routes["baseline"]

    assert len(baseline) == len(routes["optimized"])
    cruise_points = [
        point for point in baseline
        if point["phase"] == "cruise"
    ]
    assert cruise_points
    baseline_nodes = [point for point in baseline if point["pressure_level"] is not None]
    assert baseline_nodes
    assert all(point["pressure_level"] == 250 for point in baseline_nodes)
    assert any(point["altitude_km"] == pytest.approx(10.4) for point in cruise_points)
    latitude_delta = ROUTE["destination"]["lat"] - ROUTE["origin"]["lat"]
    for point in baseline:
        fraction = (point["lat"] - ROUTE["origin"]["lat"]) / latitude_delta
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
    assert len(payload["grid"]) > 100
    assert sum(event["cell_count"] for event in payload["events"]) > len(payload["grid"]) * 0.85
    assert payload["routes"]["optimized"]


def test_synthetic_scenario_endpoint_rejects_unknown_scenario():
    response = client.get("/test-scenarios/tornadoes")

    assert response.status_code == 404
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
