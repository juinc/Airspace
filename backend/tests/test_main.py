from fastapi.testclient import TestClient

import main

client = TestClient(main.app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_default_scene_grid_covers_romania_bounds():
    config = main.DEFAULT_CONFIG
    map_bounds = main.ROMANIA_MAP_GEO_BOUNDS
    points = main.build_horizontal_grid(
        config["min_lat"], config["max_lat"],
        config["min_lon"], config["max_lon"],
        config["lat_step"], config["lon_step"],
    )

    assert len(points) == 861
    assert config["min_lat"] <= map_bounds["min_lat"]
    assert config["max_lat"] >= map_bounds["max_lat"]
    assert config["min_lon"] <= map_bounds["min_lon"]
    assert config["max_lon"] >= map_bounds["max_lon"]


def test_test_weather_endpoint_uses_fetch_and_parse(monkeypatch):
    fake_parsed = [{"lat": 44.57, "lon": 26.10, "forecast_time": "2024-01-01T00:00", "levels": {}}]

    monkeypatch.setattr(main, "load_cache", lambda key: None)
    monkeypatch.setattr(main, "save_cache", lambda key, payload: None)
    monkeypatch.setattr(main, "fetch_forecast", lambda lat, lon: {"hourly": {"time": []}})
    monkeypatch.setattr(main, "parse_response", lambda raw, lat, lon, levels: fake_parsed)

    response = client.get("/test-weather")

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "live"
    assert body["data"] == fake_parsed


def test_test_weather_endpoint_returns_cache_when_available(monkeypatch):
    monkeypatch.setattr(main, "load_cache", lambda key: [{"cached": True}])

    response = client.get("/test-weather")

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "cache"
    assert body["data"] == [{"cached": True}]


def test_weather_grid_test_mode_limits_to_four_points(monkeypatch):
    monkeypatch.setattr(main, "load_cache", lambda key: None)
    monkeypatch.setattr(main, "save_cache", lambda key, payload: None)
    monkeypatch.setattr(main, "fetch_forecast", lambda lat, lon: {"hourly": {"time": []}})
    monkeypatch.setattr(main, "parse_response", lambda raw, lat, lon, levels: [{} for _ in lat])

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
        lambda raw, latitudes, longitudes, levels: [
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
        return {}, grid

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