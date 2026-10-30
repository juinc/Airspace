import numpy as np


def build_horizontal_grid(min_lat, max_lat, min_lon, max_lon, lat_step, lon_step):
    """
    Returns the 2D grid of (lat, lon) positions only.
    Pressure levels are added later from the API response, not multiplied
    here, since one request per point already returns all levels.
    """
    lats = np.arange(min_lat, max_lat + lat_step / 2, lat_step)
    lons = np.arange(min_lon, max_lon + lon_step / 2, lon_step)

    points = []
    for lat in lats:
        for lon in lons:
            points.append({"lat": round(float(lat), 4), "lon": round(float(lon), 4)})
    return points