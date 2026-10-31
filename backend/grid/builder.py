import numpy as np


def build_horizontal_grid(min_lat, max_lat, min_lon, max_lon, lat_step, lon_step):
    if lat_step <= 0 or lon_step <= 0:
        raise ValueError("lat_step and lon_step must be greater than 0")
    if max_lat <= min_lat or max_lon <= min_lon:
        raise ValueError("max_lat/max_lon must be greater than min_lat/min_lon")

    lats = np.arange(min_lat, max_lat + lat_step / 2, lat_step)
    lons = np.arange(min_lon, max_lon + lon_step / 2, lon_step)

    points = []
    for lat in lats:
        for lon in lons:
            points.append({"lat": round(float(lat), 4), "lon": round(float(lon), 4)})
    return points