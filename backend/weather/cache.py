import json
import os
import time

CACHE_DIR = "runtime/cache"
CACHE_FILE = os.path.join(CACHE_DIR, "weather_cache.json")
TTL_SECONDS = 6 * 60 * 60  # matches AIFS 6-hour forecast step


def _ensure_dir():
    os.makedirs(CACHE_DIR, exist_ok=True)


def load_cache(key: str):
    _ensure_dir()
    if not os.path.exists(CACHE_FILE):
        return None
    with open(CACHE_FILE, "r") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            return None
    entry = data.get(key)
    if not entry:
        return None
    if time.time() - entry["timestamp"] > TTL_SECONDS:
        return None
    return entry["payload"]


def save_cache(key: str, payload):
    _ensure_dir()
    data = {}
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = {}
    data[key] = {"timestamp": time.time(), "payload": payload}
    with open(CACHE_FILE, "w") as f:
        json.dump(data, f)