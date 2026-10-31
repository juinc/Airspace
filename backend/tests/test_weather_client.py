from datetime import datetime, timezone

import pytest

from weather.client import (
    OPEN_METEO_URL,
    build_variable_list,
    fetch_forecast,
    parse_response,
    select_forecast_index,
)


def test_fetch_forecast_posts_all_coordinates_in_json_body(monkeypatch):
    calls = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"hourly": {"time": []}}

    def fake_post(url, json, timeout):
        calls["url"] = url
        calls["json"] = json
        calls["timeout"] = timeout
        return FakeResponse()

    def reject_get(*args, **kwargs):
        raise AssertionError("Forecast requests should use a JSON body, not a URL query.")

    monkeypatch.setattr("weather.client.requests.post", fake_post)
    monkeypatch.setattr("weather.client.requests.get", reject_get)

    result = fetch_forecast([43.5, 43.75], [20.0, 20.25])

    assert result == {"hourly": {"time": []}}
    assert calls["url"] == OPEN_METEO_URL
    assert calls["json"]["latitude"] == [43.5, 43.75]
    assert calls["json"]["longitude"] == [20.0, 20.25]
    assert calls["json"]["hourly"] == build_variable_list()
    assert calls["json"]["models"] == ["ecmwf_aifs025_single"]
    assert calls["json"]["forecast_days"] == 2
    assert calls["json"]["past_days"] == 0
    assert calls["json"]["timezone"] == ["GMT", "GMT"]
    assert calls["timeout"] == 30


def test_select_forecast_index_chooses_next_future_six_hour_step():
    raw = {
        "hourly": {
            "time": [
                "2026-10-31T12:00",
                "2026-10-31T15:00",
                "2026-10-31T18:00",
                "2026-11-01T00:00",
            ]
        }
    }
    now = datetime(2026, 10, 31, 15, 30, tzinfo=timezone.utc)

    assert select_forecast_index(raw, now) == 2


def test_select_forecast_index_rejects_responses_without_future_aifs_steps():
    raw = {"hourly": {"time": ["2026-10-31T12:00", "2026-10-31T15:00"]}}
    now = datetime(2026, 10, 31, 15, 30, tzinfo=timezone.utc)

    with pytest.raises(ValueError, match="future six-hour"):
        select_forecast_index(raw, now)


def test_parse_response_preserves_vertical_velocity_for_each_level():
    raw = {
        "hourly": {
            "time": ["2026-10-31T12:00"],
            "cape": [1200],
            "precipitation": [0],
            "cloud_cover": [40],
            "vertical_velocity_300hPa": [2.1],
            "relative_humidity_300hPa": [65],
            "wind_speed_300hPa": [70],
        }
    }

    result = parse_response(raw, [45.0], [24.0], [300])

    assert result[0]["levels"][300]["vertical_velocity"] == 2.1


def test_parse_response_preserves_grid_positions_when_forecast_row_is_missing():
    raw = [
        {"hourly": {"time": ["2026-10-31T12:00"], "precipitation": [0]}},
        {"hourly": {"time": []}},
    ]

    result = parse_response(raw, [45.0, 45.25], [24.0, 24.25], [300])

    assert len(result) == 2
    assert result[1]["lat"] == 45.25
    assert result[1]["forecast_time"] is None
    assert result[1]["levels"][300]["exposure_score"] is None