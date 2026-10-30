from weather.normalize import normalize, weather_exposure_score


def test_normalize_returns_none_for_missing_value():
    assert normalize(None, 0, 10) is None


def test_normalize_clamps_out_of_range_values():
    assert normalize(-5, 0, 10) == 0
    assert normalize(15, 0, 10) == 1


def test_normalize_mid_value():
    assert normalize(5, 0, 10) == 0.5


def test_exposure_score_all_values_at_max_is_100():
    score = weather_exposure_score(
        cape=3000, precipitation=20, vertical_velocity=3, humidity=100, cloud_cover=100
    )
    assert score == 100.0


def test_exposure_score_all_values_at_zero_is_0():
    score = weather_exposure_score(
        cape=0, precipitation=0, vertical_velocity=0, humidity=0, cloud_cover=0
    )
    assert score == 0.0


def test_exposure_score_all_missing_returns_none():
    assert weather_exposure_score() is None


def test_exposure_score_vertical_velocity_uses_absolute_value():
    positive = weather_exposure_score(cape=0, precipitation=0, vertical_velocity=3, humidity=0, cloud_cover=0)
    negative = weather_exposure_score(cape=0, precipitation=0, vertical_velocity=-3, humidity=0, cloud_cover=0)
    assert positive == negative == 20.0  # vertical_velocity weight is 0.20


def test_exposure_score_renormalizes_when_component_missing():
    """
    Missing cape should NOT be treated as 0 risk. The remaining weights
    (0.25 + 0.20 + 0.10 + 0.10 = 0.65) should be renormalized.
    """
    score = weather_exposure_score(
        cape=None, precipitation=20, vertical_velocity=0, humidity=0, cloud_cover=0
    )
    expected = round((0.25 / 0.65) * 100, 1)
    assert score == expected


def test_exposure_score_single_available_component_is_fully_weighted():
    score = weather_exposure_score(precipitation=20)
    assert score == 100.0