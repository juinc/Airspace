from datetime import datetime, timezone

import requests

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

PRESSURE_LEVELS = [500, 400, 300, 250, 200]
OPEN_METEO_MODEL = "ecmwf_aifs025_single"
FORECAST_STEP_HOURS = 6
FORECAST_DAYS = 2

PRESSURE_VARIABLES = [
    "temperature",
    "relative_humidity",
    "wind_speed",
    "wind_direction",
    "vertical_velocity",
    "geopotential_height",
]

SURFACE_VARIABLES = ["precipitation", "cloud_cover", "cape"]


def build_variable_list():
    variables = []
    for level in PRESSURE_LEVELS:
        for var in PRESSURE_VARIABLES:
            variables.append(f"{var}_{level}hPa")
    variables.extend(SURFACE_VARIABLES)
    return variables


def fetch_forecast(lat_list, lon_list, forecast_days=FORECAST_DAYS):
    """
    Send all parallel coordinates in one JSON-body request to avoid URL length
    limits for full-grid forecasts.
    """
    if len(lat_list) != len(lon_list):
        raise ValueError("lat_list and lon_list must be the same length")

    payload = {
        "latitude": lat_list,
        "longitude": lon_list,
        "hourly": build_variable_list(),
        "models": [OPEN_METEO_MODEL],
        "forecast_days": forecast_days,
        "past_days": 0,
        "timezone": ["GMT"] * len(lat_list),
        "timeformat": "iso8601",
    }

    response = requests.post(OPEN_METEO_URL, json=payload, timeout=30)
    try:
        response.raise_for_status()
    except requests.HTTPError as error:
        try:
            detail = response.json().get("reason", response.text[:500])
        except (ValueError, AttributeError):
            detail = response.text[:500]
        raise requests.HTTPError(
            f"Open-Meteo returned HTTP {response.status_code}: {detail}",
            response=response,
        ) from error
    return response.json()


def select_forecast_index(raw, now=None):
    """Select the first future AIFS-valid timestamp on its six-hour cadence."""
    locations = [raw] if isinstance(raw, dict) else raw
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)

    for location in locations:
        timestamps = location.get("hourly", {}).get("time", [])
        for index, timestamp in enumerate(timestamps):
            try:
                valid_time = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            except (AttributeError, TypeError, ValueError):
                continue
            if valid_time.tzinfo is None:
                valid_time = valid_time.replace(tzinfo=timezone.utc)
            valid_time = valid_time.astimezone(timezone.utc)
            if (
                valid_time >= now
                and valid_time.minute == 0
                and valid_time.second == 0
                and valid_time.hour % FORECAST_STEP_HOURS == 0
            ):
                return index

    raise ValueError("AIFS response has no future six-hour forecast timestamp")


def parse_response(raw, lat_list, lon_list, pressure_levels, forecast_index=0):
    """
    Open-Meteo returns a dict for a single location, or a list of dicts
    for multiple locations. This normalizes both cases.
    """
    from weather.normalize import weather_exposure_score

    results = []
    if forecast_index < 0:
        raise ValueError("forecast_index must be non-negative")
    locations = [raw] if isinstance(raw, dict) else raw

    for i, (lat, lon) in enumerate(zip(lat_list, lon_list)):
        location_data = locations[i] if i < len(locations) else {}
        hourly = location_data.get("hourly", {}) if isinstance(location_data, dict) else {}
        timestamps = hourly.get("time", [])
        idx = forecast_index if forecast_index < len(timestamps) else None

        point_result = {
            "lat": lat,
            "lon": lon,
            "forecast_time": timestamps[idx] if idx is not None else None,
            "levels": {},
        }

        def get_value(name):
            values = hourly.get(name)
            return values[idx] if idx is not None and values and idx < len(values) else None

        cape = get_value("cape")
        precipitation = get_value("precipitation")
        cloud_cover = get_value("cloud_cover")
        
        point_result["cape"] = cape
        point_result["precipitation"] = precipitation
        point_result["cloud_cover"] = cloud_cover

        for level in pressure_levels:
            def get(var):
                return get_value(f"{var}_{level}hPa")

            vertical_velocity = get("vertical_velocity")
            humidity = get("relative_humidity")

            score = weather_exposure_score(
                cape=cape,
                precipitation=precipitation,
                vertical_velocity=vertical_velocity,
                humidity=humidity,
                cloud_cover=cloud_cover,
            )

            point_result["levels"][level] = {
                "temperature": get("temperature"),
                "wind_speed": get("wind_speed"),
                "wind_direction": get("wind_direction"),
                "vertical_velocity": vertical_velocity,
                "geopotential_height": get("geopotential_height"),
                "relative_humidity": humidity,          # ← was missing
                "exposure_score": score,
            }

        results.append(point_result)

    return results