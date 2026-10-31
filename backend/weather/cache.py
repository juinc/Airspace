import hashlib
import json
import logging
import os
import tempfile
import threading
import time
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parents[1] / "runtime" / "cache"
CACHE_FILE = CACHE_DIR / "weather_cache.json"
TTL_SECONDS = 6 * 60 * 60
_CACHE_LOCK = threading.RLock()
_LOGGER = logging.getLogger(__name__)


def build_cache_key(namespace: str, **context) -> str:
    serialized = json.dumps(context, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return f"{namespace}:{digest}"


def _ensure_dir():
    try:
        Path(CACHE_DIR).mkdir(parents=True, exist_ok=True)
    except OSError:
        _LOGGER.warning("Unable to create weather cache directory", exc_info=True)
        return False
    return True


def _read_cache():
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as cache_file:
            data = json.load(cache_file)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_cache(data):
    if not _ensure_dir():
        return False
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=Path(CACHE_FILE).parent,
            prefix="weather-cache-",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = temporary_file.name
            json.dump(data, temporary_file, separators=(",", ":"))
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, CACHE_FILE)
        return True
    except (OSError, TypeError, ValueError):
        _LOGGER.warning("Unable to write weather cache", exc_info=True)
        if temporary_path and os.path.exists(temporary_path):
            try:
                os.remove(temporary_path)
            except OSError:
                pass
        return False


def _entry_is_fresh(entry, now):
    if not isinstance(entry, dict) or "payload" not in entry:
        return False
    try:
        timestamp = float(entry["timestamp"])
    except (KeyError, TypeError, ValueError):
        return False
    return 0 <= now - timestamp <= TTL_SECONDS


def load_cache(key: str):
    with _CACHE_LOCK:
        if not _ensure_dir():
            return None
        data = _read_cache()
        entry = data.get(key)
        now = time.time()
        if _entry_is_fresh(entry, now):
            return entry["payload"]
        if key in data:
            data.pop(key, None)
            _write_cache(data)
        return None


def save_cache(key: str, payload):
    with _CACHE_LOCK:
        if not _ensure_dir():
            return False
        now = time.time()
        data = _read_cache()
        data = {
            existing_key: entry
            for existing_key, entry in data.items()
            if _entry_is_fresh(entry, now)
        }
        data[key] = {"timestamp": now, "payload": payload}
        return _write_cache(data)