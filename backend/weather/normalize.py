import math
from typing import Optional


def normalize(value: Optional[float], min_val: float, max_val: float) -> Optional[float]:
    """Clamp and scale a raw value into 0-1. Returns None if value is missing."""
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value):
        return None
    if max_val <= min_val:
        raise ValueError("max_val must be greater than min_val")
    clamped = max(min_val, min(max_val, value))
    return (clamped - min_val) / (max_val - min_val)


def weather_exposure_score(
    cape: Optional[float] = None,
    precipitation: Optional[float] = None,
    vertical_velocity: Optional[float] = None,
    humidity: Optional[float] = None,
    cloud_cover: Optional[float] = None,
) -> Optional[float]:
    """
    0-100 exposure score. R = 0.35C + 0.25P + 0.20V + 0.10H + 0.10K

    Missing components are dropped and remaining weights are renormalized
    (NOT treated as zero risk).
    """
    components = {
        "cape": (normalize(cape, 0, 3000), 0.35),
        "precipitation": (normalize(precipitation, 0, 20), 0.25),
        "vertical_velocity": (
            normalize(abs(vertical_velocity) if vertical_velocity is not None else None, 0, 3),
            0.20,
        ),
        "humidity": (normalize(humidity, 0, 100), 0.10),
        "cloud_cover": (normalize(cloud_cover, 0, 100), 0.10),
    }

    available = {k: v for k, v in components.items() if v[0] is not None}

    if not available:
        return None  # no usable data for this cell at all

    weight_sum = sum(w for _, w in available.values())
    score = sum(val * w for val, w in available.values()) / weight_sum

    return round(score * 100, 1)