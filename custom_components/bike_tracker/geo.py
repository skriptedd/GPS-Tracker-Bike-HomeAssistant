"""Pure geometry / signal-processing helpers.

This module deliberately has no Home Assistant imports so it can be unit
tested standalone.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

EARTH_RADIUS_M = 6371008.8


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two WGS84 points, in metres."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    )
    return 2.0 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing from point 1 to point 2, in degrees (0-360)."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dlambda = math.radians(lon2 - lon1)
    y = math.sin(dlambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(
        dlambda
    )
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def speed_kmh(distance_m: float, seconds: float) -> float:
    """Convert a distance/time pair into km/h. Returns 0.0 for invalid input."""
    if seconds <= 0:
        return 0.0
    return (distance_m / seconds) * 3.6


def median(values: Sequence[float]) -> float:
    """Median of a non-empty sequence."""
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def percentile(values: Sequence[float], pct: float) -> float:
    """Linear-interpolated percentile (pct in 0..100)."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (pct / 100.0) * (len(ordered) - 1)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return ordered[int(rank)]
    return ordered[low] + (ordered[high] - ordered[low]) * (rank - low)


def median_filter(values: Sequence[float], window: int = 5) -> list[float]:
    """Sliding median filter - removes GPS altitude spikes without lag."""
    if window < 3 or len(values) < window:
        return list(values)
    if window % 2 == 0:
        window += 1
    half = window // 2
    out: list[float] = []
    for i in range(len(values)):
        lo = max(0, i - half)
        hi = min(len(values), i + half + 1)
        out.append(median(values[lo:hi]))
    return out


def moving_average(values: Sequence[float], window: int = 5) -> list[float]:
    """Centred moving average - kills the alternating jitter a median filter
    leaves behind."""
    if window < 2 or len(values) < window:
        return list(values)
    half = window // 2
    out: list[float] = []
    for i in range(len(values)):
        lo = max(0, i - half)
        hi = min(len(values), i + half + 1)
        chunk = values[lo:hi]
        out.append(sum(chunk) / len(chunk))
    return out


def elevation_stats(
    altitudes: Sequence[float | None], threshold_m: float = 3.0
) -> tuple[float, float, float | None, float | None]:
    """Return (gain_m, loss_m, min_m, max_m) from a series of altitudes.

    Raw GPS altitude is noisy (+/- 10 m is normal), so summing every delta
    massively over-reports climbing. Three stages fix that:

    1. a median filter removes single-sample spikes,
    2. a moving average removes the remaining high-frequency jitter,
    3. hysteresis only accumulates once the deviation from the last accepted
       reference exceeds ``threshold_m`` - the approach bike computers use.
    """
    clean = [a for a in altitudes if a is not None and -500.0 < a < 9000.0]
    if len(clean) < 2:
        return 0.0, 0.0, None, None

    smoothed = moving_average(median_filter(clean, 5), 5)
    gain = 0.0
    loss = 0.0
    reference = smoothed[0]
    for value in smoothed[1:]:
        delta = value - reference
        if delta > threshold_m:
            gain += delta
            reference = value
        elif delta < -threshold_m:
            loss += -delta
            reference = value
    return gain, loss, min(smoothed), max(smoothed)


def simplify(
    points: Sequence[tuple[float, float]], tolerance_m: float = 5.0
) -> list[tuple[float, float]]:
    """Ramer-Douglas-Peucker simplification, for sending tracks to the UI."""
    if len(points) < 3:
        return list(points)

    def perpendicular_distance(
        pt: tuple[float, float],
        start: tuple[float, float],
        end: tuple[float, float],
    ) -> float:
        # Local flat-earth projection is fine at these scales.
        lat_scale = 111320.0
        lon_scale = 111320.0 * math.cos(math.radians(start[0]))
        x0 = (pt[1] - start[1]) * lon_scale
        y0 = (pt[0] - start[0]) * lat_scale
        x1 = (end[1] - start[1]) * lon_scale
        y1 = (end[0] - start[0]) * lat_scale
        seg_len_sq = x1 * x1 + y1 * y1
        if seg_len_sq == 0:
            return math.hypot(x0, y0)
        t = max(0.0, min(1.0, (x0 * x1 + y0 * y1) / seg_len_sq))
        return math.hypot(x0 - t * x1, y0 - t * y1)

    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        first, last = stack.pop()
        if last <= first + 1:
            continue
        max_dist = 0.0
        index = first
        for i in range(first + 1, last):
            dist = perpendicular_distance(points[i], points[first], points[last])
            if dist > max_dist:
                max_dist = dist
                index = i
        if max_dist > tolerance_m:
            keep[index] = True
            stack.append((first, index))
            stack.append((index, last))
    return [p for p, k in zip(points, keep, strict=True) if k]


def bounding_box(
    points: Sequence[tuple[float, float]],
) -> tuple[float, float, float, float] | None:
    """Return (min_lat, min_lon, max_lat, max_lon)."""
    if not points:
        return None
    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    return min(lats), min(lons), max(lats), max(lons)
