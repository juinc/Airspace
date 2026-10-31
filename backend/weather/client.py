import requests

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

PRESSURE_LEVELS = [400, 300, 250, 200]

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


def fetch_forecast(lat_list, lon_list, forecast_days=2):
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
        "models": ["ecmwf_aifs025_single"],
        "forecast_days": forecast_days,
        "timeformat": "iso8601",
    }

    response = requests.post(OPEN_METEO_URL, json=payload, timeout=30)
    response.raise_for_status()
    return response.json()


def parse_response(raw, lat_list, lon_list, pressure_levels, forecast_index=0):
    """
    Open-Meteo returns a dict for a single location, or a list of dicts
    for multiple locations. This normalizes both cases.
    """
    from weather.normalize import weather_exposure_score

    if isinstance(raw, dict):
        raw = [raw]

    results = []

    for i, location_data in enumerate(raw):
        hourly = location_data.get("hourly", {})
        timestamps = hourly.get("time", [])
        if not timestamps:
            continue

        idx = min(forecast_index, len(timestamps) - 1)

        point_result = {
            "lat": lat_list[i],
            "lon": lon_list[i],
            "forecast_time": timestamps[idx],
            "levels": {},
        }

        cape = hourly.get("cape", [None] * len(timestamps))[idx]
        precipitation = hourly.get("precipitation", [None] * len(timestamps))[idx]
        cloud_cover = hourly.get("cloud_cover", [None] * len(timestamps))[idx]
        
        point_result["cape"] = cape
        point_result["precipitation"] = precipitation
        point_result["cloud_cover"] = cloud_cover

        for level in pressure_levels:
            def get(var):
                arr = hourly.get(f"{var}_{level}hPa")
                return arr[idx] if arr else None

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
                "geopotential_height": get("geopotential_height"),
                "exposure_score": score,
            }

        results.append(point_result)

    return results