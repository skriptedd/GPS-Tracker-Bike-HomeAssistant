"""Tests for the geometry helpers."""

import math

import pytest
from bt.geo import (
    bounding_box,
    elevation_stats,
    haversine,
    median_filter,
    moving_average,
    percentile,
    simplify,
    speed_kmh,
)

BERLIN = (52.520008, 13.404954)
POTSDAM = (52.390569, 13.064473)


def test_haversine_known_distance():
    # Berlin -> Potsdam is roughly 27 km.
    distance = haversine(*BERLIN, *POTSDAM)
    assert 26000 < distance < 28000


def test_haversine_zero():
    assert haversine(*BERLIN, *BERLIN) == 0.0


def test_haversine_one_degree_latitude():
    # One degree of latitude is ~111.2 km anywhere on earth.
    assert math.isclose(haversine(0, 0, 1, 0), 111195, rel_tol=0.01)


def test_speed_kmh():
    assert speed_kmh(1000, 3600) == 1.0
    assert speed_kmh(100, 0) == 0.0


def test_percentile():
    values = list(range(1, 101))
    assert percentile(values, 50) == 50.5
    assert percentile(values, 85) == pytest.approx(85.15)
    assert percentile([], 50) == 0.0
    assert percentile([7], 99) == 7


def test_median_filter_removes_spike():
    values = [10, 10, 10, 90, 10, 10, 10]
    filtered = median_filter(values, 5)
    assert max(filtered) == 10


def test_moving_average_smooths_jitter():
    alternating = [100 + (2 if i % 2 else -2) for i in range(40)]
    smoothed = moving_average(alternating, 5)
    assert max(smoothed) - min(smoothed) < 1.5


def test_elevation_stats_ignores_noise():
    # Pure noise around 100 m must not produce elevation gain.
    noisy = [100 + (1 if i % 2 else -1) * 2.0 for i in range(60)]
    gain, loss, low, high = elevation_stats(noisy, threshold_m=3.0)
    assert gain == 0.0
    assert loss == 0.0
    assert low is not None and high is not None


def test_elevation_stats_real_climb():
    # 100 m -> 200 m -> 150 m, sampled smoothly.
    up = [100 + i for i in range(101)]
    down = [200 - i for i in range(51)]
    gain, loss, low, high = elevation_stats(up + down, threshold_m=3.0)
    # Smoothing shaves the peak slightly, so allow a small margin.
    assert 85 < gain < 105
    assert 40 < loss < 55
    assert 100 <= low < 105 and 195 < high <= 200


def test_elevation_stats_needs_data():
    assert elevation_stats([]) == (0.0, 0.0, None, None)
    assert elevation_stats([None, None]) == (0.0, 0.0, None, None)


def test_simplify_keeps_shape():
    line = [(52.0 + i * 0.0001, 13.0) for i in range(100)]
    simplified = simplify(line, tolerance_m=5.0)
    assert len(simplified) < len(line)
    assert simplified[0] == line[0]
    assert simplified[-1] == line[-1]


def test_bounding_box():
    assert bounding_box([]) is None
    assert bounding_box([(1.0, 2.0), (3.0, 0.0)]) == (1.0, 0.0, 3.0, 2.0)
