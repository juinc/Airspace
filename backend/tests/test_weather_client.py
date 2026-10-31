from weather.client import OPEN_METEO_URL, build_variable_list, fetch_forecast


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
    assert calls["timeout"] == 30