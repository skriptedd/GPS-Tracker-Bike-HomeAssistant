"""Synthetic GPS track generator used by the tracker tests."""

from __future__ import annotations

import math
import random

from bt.tracker import GpsPoint

EARTH_R = 6371008.8


def straight_track(
    start_ts: float,
    lat: float,
    lon: float,
    speed_kmh: float,
    duration_s: float,
    interval_s: float = 10.0,
    accuracy: float = 8.0,
    noise_m: float = 0.0,
    altitude_start: float | None = None,
    altitude_rate_m_per_km: float = 0.0,
    seed: int = 7,
) -> list[GpsPoint]:
    """Generate points moving due east at a constant speed."""
    rng = random.Random(seed)
    points: list[GpsPoint] = []
    metres_per_second = speed_kmh / 3.6
    steps = int(duration_s / interval_s)
    current_lat, current_lon = lat, lon
    travelled = 0.0
    altitude = altitude_start

    for step in range(steps + 1):
        jitter_lat = rng.gauss(0, noise_m) / 111320.0 if noise_m else 0.0
        jitter_lon = (
            rng.gauss(0, noise_m) / (111320.0 * math.cos(math.radians(lat)))
            if noise_m
            else 0.0
        )
        points.append(
            GpsPoint(
                ts=start_ts + step * interval_s,
                lat=current_lat + jitter_lat,
                lon=current_lon + jitter_lon,
                alt=altitude,
                accuracy=accuracy,
            )
        )
        delta_m = metres_per_second * interval_s
        travelled += delta_m
        current_lon += delta_m / (111320.0 * math.cos(math.radians(current_lat)))
        if altitude is not None:
            altitude += altitude_rate_m_per_km * (delta_m / 1000.0)
    return points


def standstill(
    start_ts: float, lat: float, lon: float, duration_s: float, interval_s: float = 10.0
) -> list[GpsPoint]:
    """Generate points that do not move."""
    steps = int(duration_s / interval_s)
    return [
        GpsPoint(ts=start_ts + i * interval_s, lat=lat, lon=lon, alt=None, accuracy=8.0)
        for i in range(steps + 1)
    ]
