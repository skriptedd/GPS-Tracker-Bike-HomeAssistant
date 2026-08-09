"""Tests for the activity classifier."""

import random

from bt.classify import classify
from bt.const import ACTIVITY_BIKE, ACTIVITY_CAR, ACTIVITY_UNKNOWN, ACTIVITY_WALK


def _series(mean, jitter, n=200, stops=0):
    random.seed(42)
    values = [max(0.0, random.gauss(mean, jitter)) for _ in range(n)]
    return [0.0] * stops + values


def test_walking():
    result = classify(_series(4.8, 0.8))
    assert result.activity == ACTIVITY_WALK
    assert result.confidence > 0.5


def test_city_cycling():
    result = classify(_series(19.0, 4.0, stops=30))
    assert result.activity == ACTIVITY_BIKE


def test_fast_cycling_with_descent():
    speeds = [*_series(27.0, 5.0, stops=10), 55.0, 58.0, 52.0]
    assert classify(speeds).activity == ACTIVITY_BIKE


def test_car_motorway():
    assert classify(_series(95.0, 12.0)).activity == ACTIVITY_CAR


def test_car_in_town():
    # Lots of stops, but peaks well above bicycle range.
    speeds = [*_series(42.0, 9.0, stops=60), 72.0, 78.0]
    assert classify(speeds).activity == ACTIVITY_CAR


def test_too_little_data():
    assert classify([1.0, 2.0]).activity == ACTIVITY_UNKNOWN
    assert classify([0.0] * 50).activity == ACTIVITY_UNKNOWN


def test_features_are_reported():
    result = classify(_series(20.0, 3.0), distance_m=5000, duration_s=900)
    assert set(result.features) >= {"p50", "p85", "peak", "stop_ratio"}
