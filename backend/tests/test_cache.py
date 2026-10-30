import time

import weather.cache as cache_module


def _point_cache_at(monkeypatch, tmp_path):
    monkeypatch.setattr(cache_module, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(cache_module, "CACHE_FILE", str(tmp_path / "weather_cache.json"))


def test_cache_roundtrip(tmp_path, monkeypatch):
    _point_cache_at(monkeypatch, tmp_path)
    cache_module.save_cache("mykey", {"foo": "bar"})
    assert cache_module.load_cache("mykey") == {"foo": "bar"}


def test_cache_missing_key_returns_none(tmp_path, monkeypatch):
    _point_cache_at(monkeypatch, tmp_path)
    assert cache_module.load_cache("does-not-exist") is None


def test_cache_expired_entry_returns_none(tmp_path, monkeypatch):
    _point_cache_at(monkeypatch, tmp_path)
    cache_module.save_cache("k", {"a": 1})

    future = time.time() + cache_module.TTL_SECONDS + 10
    monkeypatch.setattr(cache_module.time, "time", lambda: future)

    assert cache_module.load_cache("k") is None


def test_cache_corrupted_file_does_not_crash(tmp_path, monkeypatch):
    _point_cache_at(monkeypatch, tmp_path)
    cache_file = tmp_path / "weather_cache.json"
    cache_file.write_text("not valid json {{{")
    assert cache_module.load_cache("anything") is None