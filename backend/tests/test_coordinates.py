import math

from grid.coordinates import (
    meters_per_degree_longitude,
    latlon_to_scene_xz,
    altitude_to_scene_y,
    resolve_altitude_m,
    attach_scene_coordinates,
    GRID_ORIGIN_LAT,
    GRID_ORIGIN_LON,
)


def test_origin_maps_to_zero_zero():
    x, z = latlon_to_scene_xz(GRID_ORIGIN_LAT, GRID_ORIGIN_LON)
    assert x == 0.0
    assert z == 0.0


def test_one_degree_north_is_about_111km():
    x, z = latlon_to_scene_xz(GRID_ORIGIN_LAT + 1.0, GRID_ORIGIN_LON)
    assert x == 0.0
    assert math.isclose(z, 111.32, rel_tol=1e-3)


def test_one_degree_east_is_less_than_111km_due_to_latitude():
    x, z = latlon_to_scene_xz(GRID_ORIGIN_LAT, GRID_ORIGIN_LON + 1.0)
    assert z == 0.0
    assert 0 < x < 111.32  # shrunk by cos(latitude)


def test_south_and_west_produce_negative_coordinates():
    x, z = latlon_to_scene_xz(GRID_ORIGIN_LAT - 1.0, GRID_ORIGIN_LON - 1.0)
    assert x < 0
    assert z < 0


def test_altitude_to_scene_y_applies_exaggeration():
    y = altitude_to_scene_y(9200, exaggeration=20)
    assert y == 184.0  # 9.2km * 20


def test_resolve_altitude_prefers_real_geopotential_height():
    level_data = {"geopotential_height": 9300}
    assert resolve_altitude_m(level_data, 300) == 9300


def test_resolve_altitude_falls_back_when_missing():
    level_data = {"geopotential_height": None}
    assert resolve_altitude_m(level_data, 300) == 9200


def test_attach_scene_coordinates_adds_expected_fields():
    grid_points = [
        {
            "lat": GRID_ORIGIN_LAT,
            "lon": GRID_ORIGIN_LON,
            "levels": {
                300: {"geopotential_height": 9200},
            },
        }
    ]

    result = attach_scene_coordinates(grid_points, [300])

    point = result[0]
    assert point["x"] == 0.0
    assert point["z"] == 0.0
    assert point["levels"][300]["altitude_km"] == 9.2
    assert point["levels"][300]["y"] == 184.0


def test_attach_scene_coordinates_handles_missing_level_gracefully():
    grid_points = [{"lat": 0, "lon": 0, "levels": {}}]
    result = attach_scene_coordinates(grid_points, [300])
    # should not crash, and should simply not add level-specific data
    assert "x" in result[0]
    assert "z" in result[0]