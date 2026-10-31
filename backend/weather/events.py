import numpy as np
from scipy import ndimage
from grid.coordinates import (
    FALLBACK_ALTITUDE_M,
    altitude_to_scene_y,
    latlon_to_scene_xz,
    resolve_altitude_m,
)

THRESHOLDS = {
    "rain_mm": 1.0,
    "storm_precip_mm": 4.0,
    "cape_thunderstorm": 1000,
    "cape_severe": 2500,
    "vertical_velocity_strong": 1.5,
    "wind_speed_severe_kmh": 100,
}


def classify_point(cape, precipitation, vertical_velocity, wind_speed):
    """
    Coarse proxy classification from AIFS (~28km) model fields.
    NOT radar-based nowcasting. Cannot resolve tornado-scale circulation.
    """
    cape = _finite_weather_value(cape)
    precipitation = _finite_weather_value(precipitation)
    vertical_velocity = _finite_weather_value(vertical_velocity)
    wind_speed = _finite_weather_value(wind_speed)
    vv = abs(vertical_velocity) if vertical_velocity is not None else 0
    is_convective = (
        cape is not None
        and vertical_velocity is not None
        and cape >= THRESHOLDS["cape_thunderstorm"]
        and vv >= THRESHOLDS["vertical_velocity_strong"]
    )

    if is_convective and (
        cape >= THRESHOLDS["cape_severe"]
        or (wind_speed is not None and wind_speed >= THRESHOLDS["wind_speed_severe_kmh"])
    ):
        return "severe_storm"
    if is_convective:
        return "thunderstorm"
    if precipitation is not None and precipitation >= THRESHOLDS["rain_mm"]:
        return "rain"
    if cape is None or precipitation is None or vertical_velocity is None:
        return "unknown"
    return "clear"


def _finite_weather_value(value):
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if np.isfinite(value) else None


def build_classification_grid(grid_points, n_lats, n_lons, level):
    """
    Returns a 2D array of string labels shaped (n_lats, n_lons), matching
    the row-major order the grid builder produces (lat outer loop, lon inner).
    """
    labels = np.empty((n_lats, n_lons), dtype=object)
    for i, point in enumerate(grid_points):
        row, col = divmod(i, n_lons)
        levels = point.get("levels", {})
        level_data = levels.get(level, levels.get(str(level), {}))
        labels[row, col] = classify_point(
            cape=level_data.get("cape", point.get("cape")),
            precipitation=level_data.get("precipitation", point.get("precipitation")),
            vertical_velocity=level_data.get("vertical_velocity"),
            wind_speed=level_data.get("wind_speed"),
        )
    return labels


def detect_events(grid_points, n_lats, n_lons, lat_values, lon_values, level, target_label):
    """
    Groups adjacent cells matching target_label into discrete events
    with a real lat/lon position (centroid) and extent.
    """
    labels = build_classification_grid(grid_points, n_lats, n_lons, level)
    mask = (labels == target_label)

    labeled_array, num_features = ndimage.label(
        mask, structure=np.ones((3, 3), dtype=int)
    )
        
    events = []
    for feature_id in range(1, num_features + 1):
        rows, cols = np.where(labeled_array == feature_id)
        cells = [
            (grid_points[row * n_lons + col], row, col)
            for row, col in zip(rows, cols)
            if row * n_lons + col < len(grid_points)
        ]
        if not cells:
            continue

        cell_latitudes = [
            point.get("lat", lat_values[row]) for point, row, _ in cells
        ]
        cell_longitudes = [
            point.get("lon", lon_values[col]) for point, _, col in cells
        ]
        centroid_lat = float(np.mean(cell_latitudes))
        centroid_lon = float(np.mean(cell_longitudes))
        x, z = latlon_to_scene_xz(centroid_lat, centroid_lon)
        altitude_values_km = []
        for point, _, _ in cells:
            level_data = point.get("levels", {}).get(
                level, point.get("levels", {}).get(str(level), {})
            )
            altitude_km = level_data.get("altitude_km")
            if altitude_km is None:
                altitude_m = resolve_altitude_m(level_data, level)
                if altitude_m is not None:
                    altitude_km = altitude_m / 1000
            if altitude_km is not None and np.isfinite(altitude_km):
                altitude_values_km.append(float(altitude_km))
        altitude_km = (
            float(np.median(altitude_values_km))
            if altitude_values_km
            else FALLBACK_ALTITUDE_M.get(level, 9200) / 1000
        )
        y = altitude_to_scene_y(altitude_km * 1000)
        precipitation_values = [
            point.get("precipitation")
            for point, _, _ in cells
            if point.get("precipitation") is not None
        ]
        maximum_precipitation = max(precipitation_values, default=None)

        events.append({
            "type": target_label,
            "severity": (
                "heavy"
                if target_label == "rain"
                and maximum_precipitation is not None
                and maximum_precipitation >= THRESHOLDS["storm_precip_mm"]
                else "light"
                if target_label == "rain"
                else None
            ),
            "level_hpa": level,
            "centroid": {
                "lat": centroid_lat,
                "lon": centroid_lon,
                "x": x,
                "y": y,
                "altitude_km": altitude_km,
                "z": z,
            },
            "cell_count": int(len(rows)),
            "bounding_box": {
                "min_lat": float(min(cell_latitudes)),
                "max_lat": float(max(cell_latitudes)),
                "min_lon": float(min(cell_longitudes)),
                "max_lon": float(max(cell_longitudes)),
            },
        })
    return events