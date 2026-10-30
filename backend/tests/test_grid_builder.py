from grid.builder import build_horizontal_grid


def test_full_corridor_grid_has_288_points():
    """Matches the documented active_grid config: 16 lat steps × 18 lon steps."""
    points = build_horizontal_grid(43.75, 47.50, 22.75, 27.00, 0.25, 0.25)
    assert len(points) == 288


def test_small_grid_exact_values():
    points = build_horizontal_grid(0, 1, 0, 1, 1, 1)
    assert points == [
        {"lat": 0.0, "lon": 0.0},
        {"lat": 0.0, "lon": 1.0},
        {"lat": 1.0, "lon": 0.0},
        {"lat": 1.0, "lon": 1.0},
    ]


def test_grid_points_are_rounded_floats():
    points = build_horizontal_grid(0, 0.3, 0, 0.3, 0.1, 0.1)
    for p in points:
        assert isinstance(p["lat"], float)
        assert isinstance(p["lon"], float)