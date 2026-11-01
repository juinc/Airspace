import pytest
from fastapi.testclient import TestClient

import main

client = TestClient(main.app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_default_scene_grid_uses_the_requested_288_point_region():
    config = main.DEFAULT_CONFIG
    points = main.build_horizontal_grid(
        config["min_lat"], config["max_lat"],
        config["min_lon"], config["max_lon"],
        config["lat_step"], config["lon_step"],
    )

    assert len(points) == 288
    assert (config["min_lat"], config["max_lat"]) == (43.75, 47.50)
    assert (config["min_lon"], config["max_lon"]) == (22.75, 27.00)
    assert config["lat_step"] == config["lon_step"] == 0.25
    assert all(
        config["min_lat"] <= airport["lat"] <= config["max_lat"]
        and config["min_lon"] <= airport["lon"] <= config["max_lon"]
        for airport in main.ROUTE.values()
    )


def test_test_weather_endpoint_uses_fetch_and_parse(monkeypatch):
    fake_parsed = [{"lat": 44.57, "lon": 26.10, "forecast_time": "2024-01-01T00:00", "levels": {}}]

    monkeypatch.setattr(main, "load_cache", lambda key: None)
    monkeypatch.setattr(main, "save_cache", lambda key, payload: None)
    monkeypatch.setattr(main, "fetch_forecast", lambda lat, lon: {"hourly": {"time": []}})
    monkeypatch.setattr(
        main,
        "parse_response",
        lambda raw, lat, lon, levels, forecast_index=0: fake_parsed,
    )
    monkeypatch.setattr(main, "select_forecast_index", lambda raw: 0)

    response = client.get("/test-weather")

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "live"
    assert body["data"] == fake_parsed


def test_test_weather_endpoint_returns_cache_when_available(monkeypatch):
    cached = {"hourly": {"time": ["2026-10-31T18:00"]}}
    monkeypatch.setattr(main, "load_cache", lambda key: cached)
    monkeypatch.setattr(main, "select_forecast_index", lambda raw: 0)

    response = client.get("/test-weather")

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "cache"
    assert body["data"][0]["lat"] == main.ROUTE["origin"]["lat"]
    assert body["data"][0]["x"] is not None


def test_weather_grid_test_mode_limits_to_four_points(monkeypatch):
    monkeypatch.setattr(main, "load_cache", lambda key: None)
    monkeypatch.setattr(main, "save_cache", lambda key, payload: None)
    monkeypatch.setattr(main, "fetch_forecast", lambda lat, lon: {"hourly": {"time": []}})
    monkeypatch.setattr(
        main,
        "parse_response",
        lambda raw, lat, lon, levels, forecast_index=0: [{} for _ in lat],
    )
    monkeypatch.setattr(main, "select_forecast_index", lambda raw: 0)

    response = client.post("/weather-grid", json={"test_mode": True})

    assert response.status_code == 200
    assert response.json()["point_count"] == 4


def test_scene_data_includes_backend_positioned_airports(monkeypatch):
    monkeypatch.setattr(main, "load_cache", lambda key: None)
    monkeypatch.setattr(main, "save_cache", lambda key, payload: None)
    monkeypatch.setattr(main, "fetch_forecast", lambda lat, lon: {})
    monkeypatch.setattr(
        main,
        "parse_response",
        lambda raw, latitudes, longitudes, levels, forecast_index=0: [
            {
                "lat": lat,
                "lon": lon,
                "forecast_time": "2026-10-31T00:00",
                "levels": {
                    level: {"geopotential_height": 10400, "exposure_score": 20}
                    for level in levels
                },
            }
            for lat, lon in zip(latitudes, longitudes)
        ],
    )
    monkeypatch.setattr(main, "select_forecast_index", lambda raw: 0)
    monkeypatch.setattr(main, "detect_events", lambda *args: [])

    response = client.post("/test-scene-data", json={"test_mode": True})

    assert response.status_code == 200
    airports = response.json()["airports"]
    assert [airport["name"] for airport in airports] == [
        "LCCR Craiova",
        "LRCL Cluj-Napoca",
    ]
    assert (airports[0]["x"], airports[0]["z"]) == main.latlon_to_scene_xz(
        main.ROUTE["origin"]["lat"], main.ROUTE["origin"]["lon"]
    )
    assert airports[0]["y"] == 0.0
    map_bounds = response.json()["meta"]["map_bounds"]
    assert (map_bounds["min_x"], map_bounds["min_z"]) == main.latlon_to_scene_xz(
        main.ROMANIA_MAP_GEO_BOUNDS["min_lat"], main.ROMANIA_MAP_GEO_BOUNDS["min_lon"]
    )
    assert (map_bounds["max_x"], map_bounds["max_z"]) == main.latlon_to_scene_xz(
        main.ROMANIA_MAP_GEO_BOUNDS["max_lat"], main.ROMANIA_MAP_GEO_BOUNDS["max_lon"]
    )
    assert response.json()["meta"]["trajectory_status"].startswith("A* optimized route")
    assumptions = response.json()["meta"]["routing_assumptions"]
    aircraft_profile = assumptions["aircraft_profile"]
    assert aircraft_profile["aircraft_name"] == "Cessna Citation CJ3"
    assert aircraft_profile["aircraft_variant"] == "CJ3 (original)"
    assert aircraft_profile["cruise_speed_kmh"] == pytest.approx(416 * 1.852)
    assert aircraft_profile["fuel_capacity_kg"] == pytest.approx(2136.4)
    assert "not POH" in aircraft_profile["fuel_burn_basis"]
    assert assumptions["climb_descent_model"] == "parallel_climb_max_time"
    assert assumptions["operational_collision_avoidance"] is False
    assert assumptions["terrain_clearance_validated"] is False
    assert len(response.json()["routes"]["baseline"]) == len(
        response.json()["routes"]["optimized"]
    )
    assert "avoided_high_exposure_cells" in response.json()["routes"]["reasoning"]


def test_optimize_endpoint_returns_routes_for_selected_mode(monkeypatch):
    grid = main.attach_scene_coordinates(
        [
            {
                "lat": 45.5,
                "lon": 23.75,
                "levels": {
                    level: {
                        "geopotential_height": 10400,
                        "exposure_score": None,
                    }
                    for level in main.PRESSURE_LEVELS
                },
            }
        ],
        main.PRESSURE_LEVELS,
    )
    requested_test_modes = []

    def fake_scene_grid(req):
        requested_test_modes.append(req.test_mode)
        return {}, grid, "live"

    monkeypatch.setattr(main, "_scene_grid", fake_scene_grid)

    response = client.post("/optimize", json={"mode": "Lower-exposure"})

    assert response.status_code == 200
    assert requested_test_modes == [False]
    routes = response.json()
    assert routes["reasoning"]["mode"] == "lower-exposure"
    assert len(routes["baseline"]) == len(routes["optimized"])
    assert routes["metrics"]["optimized"]["avg_exposure"] is None


def test_optimize_endpoint_rejects_unknown_mode():
    response = client.post("/optimize", json={"mode": "Storm chaser"})

    assert response.status_code == 400
    assert response.json()["detail"] == "mode must be Fastest, Balanced, or Lower-exposure"


def test_scene_endpoint_allows_local_frontend_cors():
    response = client.options(
        "/test-scene-data",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_real_meteo_scenario_uses_full_live_scene(monkeypatch):
    requests = []

    def fake_scene_data(req):
        requests.append(req)
        return {"meta": {"source": "live"}}

    monkeypatch.setattr(main, "test_scene_data", fake_scene_data)

    response = client.get("/test-scenarios/real-meteo?mode=Lower-exposure")

    assert response.status_code == 200
    assert requests[0].test_mode is False
    assert requests[0].mode == "Lower-exposure"
    assert response.json()["meta"]["scenario_title"] == "Open-Meteo forecast"


def test_full_scene_marks_cached_real_weather_as_cached(monkeypatch):
    monkeypatch.setattr(main, "load_cache", lambda key: {"meta": {"source": "live"}})
    monkeypatch.setattr(main, "_scene_grid", lambda req: (main.DEFAULT_CONFIG, [], "live"))

    response = client.post("/test-scene-data", json={"test_mode": False})

    assert response.status_code == 200
    assert response.json()["meta"]["source"] == "cache"


def test_cached_raw_forecast_is_parsed_at_the_selected_valid_time(monkeypatch):
    raw = {"hourly": {"time": ["2026-10-31T12:00", "2026-10-31T18:00"]}}
    parsed_indices = []
    monkeypatch.setattr(main, "load_cache", lambda key: raw)
    monkeypatch.setattr(
        main,
        "select_forecast_index",
        lambda cached: 1,
    )
    monkeypatch.setattr(
        main,
        "parse_response",
        lambda raw, latitudes, longitudes, levels, forecast_index=0: parsed_indices.append(forecast_index) or [],
    )
    monkeypatch.setattr(
        main,
        "fetch_forecast",
        lambda *args, **kwargs: pytest.fail("A valid raw cache entry should avoid a network call"),
    )

    results, source = main._fetch_weather([{"lat": 45.0, "lon": 24.0}])

    assert results == []
    assert source == "cache"
    assert parsed_indices == [1]


def test_weather_provider_error_returns_cors_enabled_502(monkeypatch):
    monkeypatch.setattr(main, "load_cache", lambda key: None)
    monkeypatch.setattr(
        main,
        "fetch_forecast",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            main.RequestException("provider rejected request")
        ),
    )

    response = client.get(
        "/test-scenarios/real-meteo",
        headers={"Origin": "http://127.0.0.1:5173"},
    )

    assert response.status_code == 502
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
    assert "provider rejected request" in response.json()["detail"]


def test_replan_endpoint_returns_new_weather_and_restarts_from_airborne_position():
    previous_grid = main.build_synthetic_grid("clear-airspace", main.DEFAULT_CONFIG)
    previous_routes = main.build_synthetic_routes(previous_grid, main.ROUTE)
    route_progress = 0.4

    response = client.post(
        "/replan",
        json={
            "previous_grid": previous_grid,
            "previous_route": previous_routes["optimized"],
            "previous_source": "synthetic",
            "grid_config": main.DEFAULT_CONFIG,
            "route_progress": route_progress,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["weather_update"]["replanned"] is True
    assert payload["meta"]["scenario"] == "drastic-weather-change"
    assert payload["routes"]["optimized"][0]["lat"] == pytest.approx(
        payload["weather_update"]["resume_position"]["lat"]
    )


def test_live_replan_uses_cached_forecast_between_aifs_cycles(monkeypatch):
    grid = main.build_synthetic_grid("clear-airspace", main.DEFAULT_CONFIG)
    route = main.build_synthetic_routes(grid, main.ROUTE)["optimized"]
    refresh_options = []

    def cached_scene(req, force_refresh=False):
        refresh_options.append(force_refresh)
        return main.DEFAULT_CONFIG, grid, "cache"

    monkeypatch.setattr(main, "_scene_grid", cached_scene)
    response = client.post(
        "/replan",
        json={
            "previous_grid": grid,
            "previous_route": route,
            "previous_source": "live",
            "grid_config": main.DEFAULT_CONFIG,
            "route_progress": 0.5,
        },
    )

    assert response.status_code == 200
    assert refresh_options == [False]
    assert response.json()["weather_update"]["replanned"] is False