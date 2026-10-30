from weather.events import detect_events
import numpy as np

@app.post("/weather-events")
def weather_events(req: GridRequest):
    cfg = {**DEFAULT_CONFIG, **{k: v for k, v in req.dict().items() if v is not None and k != "test_mode"}}

    lat_values = list(np.arange(cfg["min_lat"], cfg["max_lat"] + cfg["lat_step"]/2, cfg["lat_step"]))
    lon_values = list(np.arange(cfg["min_lon"], cfg["max_lon"] + cfg["lon_step"]/2, cfg["lon_step"]))

    points = build_horizontal_grid(cfg["min_lat"], cfg["max_lat"], cfg["min_lon"], cfg["max_lon"],
                                    cfg["lat_step"], cfg["lon_step"])
    if req.test_mode:
        points = points[:len(lat_values) * len(lon_values)]  # keep full grid, test_mode not meaningful here

    lat_list = [p["lat"] for p in points]
    lon_list = [p["lon"] for p in points]

    raw = fetch_forecast(lat_list, lon_list)
    results = parse_response(raw, lat_list, lon_list, PRESSURE_LEVELS)

    all_events = []
    for level in PRESSURE_LEVELS:
        for label in ("rain", "thunderstorm", "severe_storm"):
            all_events.extend(
                detect_events(results, len(lat_values), len(lon_values), lat_values, lon_values, level, label)
            )

    return {"events": all_events}