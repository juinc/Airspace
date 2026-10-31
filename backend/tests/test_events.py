from weather.events import classify_point, detect_events


def test_classify_point_clear():
    assert classify_point(cape=0, precipitation=0, vertical_velocity=0, wind_speed=0) == "clear"


def test_classify_point_rain():
    assert classify_point(cape=0, precipitation=2, vertical_velocity=0, wind_speed=0) == "rain"


def test_classify_point_thunderstorm():
    # convective (cape >= 1000, |vv| >= 1.5) but not severe (wind < 100, cape < 2500)
    assert classify_point(cape=1200, precipitation=0, vertical_velocity=2, wind_speed=50) == "thunderstorm"


def test_classify_point_severe_storm_via_high_cape():
    assert classify_point(cape=3000, precipitation=0, vertical_velocity=2, wind_speed=50) == "severe_storm"


def test_classify_point_severe_storm_via_high_wind():
    assert classify_point(cape=1200, precipitation=0, vertical_velocity=2, wind_speed=150) == "severe_storm"


def _make_point(cape, precipitation, cloud_cover, vertical_velocity, wind_speed, level=300):
    return {
        "cape": cape,
        "precipitation": precipitation,
        "cloud_cover": cloud_cover,
        "levels": {level: {"vertical_velocity": vertical_velocity, "wind_speed": wind_speed}},
    }


def test_detect_events_groups_adjacent_cells_into_one_cluster():
    """
    2x2 grid. Rain cells at (row0,col0) and (row1,col0) are vertically
    adjacent -> should merge into a single detected event, not two.
    """
    grid_points = [
        _make_point(cape=0, precipitation=5, cloud_cover=0, vertical_velocity=0, wind_speed=0),  # row0,col0 rain
        _make_point(cape=0, precipitation=0, cloud_cover=0, vertical_velocity=0, wind_speed=0),   # row0,col1 clear
        _make_point(cape=0, precipitation=5, cloud_cover=0, vertical_velocity=0, wind_speed=0),   # row1,col0 rain
        _make_point(cape=0, precipitation=0, cloud_cover=0, vertical_velocity=0, wind_speed=0),   # row1,col1 clear
    ]
    lat_values = [0.0, 1.0]
    lon_values = [0.0, 10.0]

    events = detect_events(grid_points, n_lats=2, n_lons=2,
                            lat_values=lat_values, lon_values=lon_values,
                            level=300, target_label="rain")

    assert len(events) == 1
    event = events[0]
    assert event["cell_count"] == 2
    assert event["centroid"]["lat"] == 0.5
    assert event["centroid"]["lon"] == 0.0


def test_detect_events_returns_empty_list_when_no_match():
    grid_points = [
        _make_point(cape=0, precipitation=0, cloud_cover=0, vertical_velocity=0, wind_speed=0)
        for _ in range(4)
    ]
    events = detect_events(grid_points, n_lats=2, n_lons=2,
                            lat_values=[0.0, 1.0], lon_values=[0.0, 1.0],
                            level=300, target_label="severe_storm")
    assert events == []


def test_detect_events_uses_level_specific_weather_when_available():
    point = _make_point(
        cape=0,
        precipitation=0,
        cloud_cover=0,
        vertical_velocity=0,
        wind_speed=0,
    )
    point["levels"][300].update(
        {"cape": 1200, "vertical_velocity": 2, "wind_speed": 50}
    )

    events = detect_events(
        [point], 1, 1, [45.0], [24.0], 300, "thunderstorm"
    )

    assert len(events) == 1