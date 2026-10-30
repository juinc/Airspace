import numpy as np
from scipy import ndimage

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
    cape = cape or 0
    precipitation = precipitation or 0
    vv = abs(vertical_velocity) if vertical_velocity is not None else 0
    wind_speed = wind_speed or 0

    is_convective = cape >= THRESHOLDS["cape_thunderstorm"] and vv >= THRESHOLDS["vertical_velocity_strong"]
    is_heavy_rain = precipitation >= THRESHOLDS["storm_precip_mm"]
    is_severe_wind = wind_speed >= THRESHOLDS["wind_speed_severe_kmh"]

    if is_convective and (is_severe_wind or cape >= THRESHOLDS["cape_severe"]):
        return "severe_storm"
    if is_convective:
        return "thunderstorm"
    if is_heavy_rain or precipitation >= THRESHOLDS["rain_mm"]:
        return "rain"
    return "clear"


def build_classification_grid(grid_points, n_lats, n_lons, level):
    """
    Returns a 2D array of string labels shaped (n_lats, n_lons), matching
    the row-major order the grid builder produces (lat outer loop, lon inner).
    """
    labels = np.empty((n_lats, n_lons), dtype=object)
    for i, point in enumerate(grid_points):
        row, col = divmod(i, n_lons)
        level_data = point["levels"][level]
        labels[row, col] = classify_point(
            cape=point.get("cape"),
            precipitation=point.get("precipitation"),
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

    labeled_array, num_features = ndimage.label(mask)

    events = []
    for feature_id in range(1, num_features + 1):
        rows, cols = np.where(labeled_array == feature_id)
        events.append({
            "type": target_label,
            "level_hpa": level,
            "centroid": {
                "lat": float(np.mean([lat_values[r] for r in rows])),
                "lon": float(np.mean([lon_values[c] for c in cols])),
            },
            "cell_count": int(len(rows)),
            "bounding_box": {
                "min_lat": float(min(lat_values[r] for r in rows)),
                "max_lat": float(max(lat_values[r] for r in rows)),
                "min_lon": float(min(lon_values[c] for c in cols)),
                "max_lon": float(max(lon_values[c] for c in cols)),
            },
        })
    return events