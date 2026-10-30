from fastapi.testclient import TestClient

import main

client = TestClient(main.app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


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