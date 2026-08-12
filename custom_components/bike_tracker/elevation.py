"""Elevation from a digital elevation model instead of the GPS altitude.

GPS altitude is the weakest number a phone produces: +/- 10 m of noise is
normal and Android frequently reports nothing at all. A DEM lookup replaces it
with a value sampled from real terrain data, which makes the elevation gain
reproducible - the same route always yields the same number.

The HTTP call is injected as a coroutine (``fetch``) rather than imported from
Home Assistant, so the batching, caching and interpolation can be unit tested
against a fake backend.

Two backends speak almost the same dialect and are auto-detected from the URL:

* **OpenTopoData** - ``GET {base}?locations=lat,lon|lat,lon``. The public
  instance is rate limited (1 request/s, 100 locations, 1000 calls/day), a
  self-hosted one is not.
* **Open-Elevation** - ``POST {base}/api/v1/lookup`` with a JSON body.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from .geo import haversine

_LOGGER = logging.getLogger(__name__)

# One request carries at most this many locations - the limit of the public
# OpenTopoData instance and a sane chunk size for a self-hosted one.
MAX_LOCATIONS_PER_REQUEST = 100

# Sampling the DEM every ~25 m is far denser than the underlying grid
# (25-90 m), so nothing is lost by not querying every single fix.
DEFAULT_SAMPLE_DISTANCE_M = 25.0

# 4 decimals ~ 11 m: fine enough to distinguish DEM cells, coarse enough that
# riding the same road twice hits the cache.
CACHE_PRECISION = 4
CACHE_MAX_ENTRIES = 200_000

# Seconds between requests. Protects the public backends from a burst when a
# long ride is processed.
DEFAULT_REQUEST_DELAY_S = 1.0

# Fetch signature: (method, url, json_body_or_None) -> decoded JSON
FetchFn = Callable[[str, str, dict[str, Any] | None], Awaitable[Any]]

LatLon = tuple[float, float]


class ElevationError(Exception):
    """The DEM backend could not be reached or answered nonsense."""


class ElevationCache:
    """Grid-rounded lat/lon -> elevation, so repeated routes cost nothing."""

    def __init__(self, max_entries: int = CACHE_MAX_ENTRIES) -> None:
        self._values: dict[tuple[float, float], float] = {}
        self._max_entries = max_entries

    @staticmethod
    def key(lat: float, lon: float) -> tuple[float, float]:
        return round(lat, CACHE_PRECISION), round(lon, CACHE_PRECISION)

    def get(self, lat: float, lon: float) -> float | None:
        return self._values.get(self.key(lat, lon))

    def put(self, lat: float, lon: float, value: float) -> None:
        if len(self._values) >= self._max_entries:
            self._values.clear()
        self._values[self.key(lat, lon)] = value

    def __len__(self) -> int:
        return len(self._values)


def sample_indices(
    points: Sequence[LatLon], min_distance_m: float = DEFAULT_SAMPLE_DISTANCE_M
) -> list[int]:
    """Indices to actually query - every ``min_distance_m`` along the track.

    First and last point are always included so the interpolation covers the
    whole track.
    """
    if not points:
        return []
    if len(points) <= 2 or min_distance_m <= 0:
        return list(range(len(points)))

    keep = [0]
    last = points[0]
    for index in range(1, len(points) - 1):
        current = points[index]
        if haversine(last[0], last[1], current[0], current[1]) >= min_distance_m:
            keep.append(index)
            last = current
    keep.append(len(points) - 1)
    return keep


def interpolate(
    total: int, indices: Sequence[int], values: Sequence[float | None]
) -> list[float | None]:
    """Spread sampled elevations back over all ``total`` track points.

    Between two samples the elevation is linearly interpolated by index, which
    is accurate enough because the samples are equidistant along the track.
    """
    if total <= 0:
        return []
    known = [(i, v) for i, v in zip(indices, values, strict=True) if v is not None]
    if not known:
        return [None] * total
    if len(known) == 1:
        return [known[0][1]] * total

    out: list[float | None] = [None] * total
    for (left_index, left_value), (right_index, right_value) in zip(
        known, known[1:], strict=False
    ):
        span = right_index - left_index
        for offset in range(span):
            ratio = offset / span if span else 0.0
            out[left_index + offset] = left_value + (right_value - left_value) * ratio
    out[known[-1][0]] = known[-1][1]

    # Extrapolate flat beyond the first and last sample.
    for index in range(known[0][0]):
        out[index] = known[0][1]
    for index in range(known[-1][0] + 1, total):
        out[index] = known[-1][1]
    return out


def build_request(
    base_url: str, coords: Sequence[LatLon]
) -> tuple[str, str, dict[str, Any] | None]:
    """Return (method, url, json_body) for the backend behind ``base_url``."""
    base = base_url.rstrip("/")
    if "open-elevation" in base or base.endswith("/api/v1/lookup"):
        url = base if base.endswith("/api/v1/lookup") else f"{base}/api/v1/lookup"
        body = {
            "locations": [
                {"latitude": round(lat, 6), "longitude": round(lon, 6)}
                for lat, lon in coords
            ]
        }
        return "POST", url, body

    locations = "|".join(f"{lat:.6f},{lon:.6f}" for lat, lon in coords)
    return "GET", f"{base}?locations={locations}", None


def parse_response(payload: Any, expected: int) -> list[float | None]:
    """Pull the elevations out of an OpenTopoData / Open-Elevation reply."""
    if not isinstance(payload, dict):
        raise ElevationError("Elevation backend returned a non-object response")

    status = payload.get("status")
    if status is not None and status != "OK":
        raise ElevationError(f"Elevation backend reported status {status}")

    results = payload.get("results")
    if not isinstance(results, list):
        raise ElevationError("Elevation backend returned no results")
    if len(results) != expected:
        raise ElevationError(
            f"Elevation backend returned {len(results)} of {expected} results"
        )

    out: list[float | None] = []
    for entry in results:
        value = entry.get("elevation") if isinstance(entry, dict) else None
        if isinstance(value, (int, float)) and -500.0 < float(value) < 9000.0:
            out.append(float(value))
        else:
            # OpenTopoData answers null for a location outside its dataset.
            out.append(None)
    return out


async def async_lookup(
    fetch: FetchFn,
    base_url: str,
    coords: Sequence[LatLon],
    cache: ElevationCache | None = None,
    request_delay_s: float = DEFAULT_REQUEST_DELAY_S,
) -> list[float | None]:
    """Resolve every coordinate to an elevation, batched and cached."""
    if not coords:
        return []

    resolved: list[float | None] = [None] * len(coords)
    pending: list[int] = []
    for index, (lat, lon) in enumerate(coords):
        cached = cache.get(lat, lon) if cache is not None else None
        if cached is not None:
            resolved[index] = cached
        else:
            pending.append(index)

    for batch_number, offset in enumerate(
        range(0, len(pending), MAX_LOCATIONS_PER_REQUEST)
    ):
        batch = pending[offset : offset + MAX_LOCATIONS_PER_REQUEST]
        if batch_number and request_delay_s > 0:
            await asyncio.sleep(request_delay_s)

        method, url, body = build_request(base_url, [coords[i] for i in batch])
        payload = await fetch(method, url, body)
        values = parse_response(payload, len(batch))
        for index, value in zip(batch, values, strict=True):
            resolved[index] = value
            if value is not None and cache is not None:
                cache.put(coords[index][0], coords[index][1], value)

    return resolved


async def async_elevations_for_track(
    fetch: FetchFn,
    base_url: str,
    track: Sequence[LatLon],
    cache: ElevationCache | None = None,
    sample_distance_m: float = DEFAULT_SAMPLE_DISTANCE_M,
    request_delay_s: float = DEFAULT_REQUEST_DELAY_S,
) -> list[float | None]:
    """DEM elevation for every point of a track.

    Only every ``sample_distance_m`` is queried; the rest is interpolated.
    """
    if not track:
        return []
    indices = sample_indices(track, sample_distance_m)
    sampled = await async_lookup(
        fetch, base_url, [track[i] for i in indices], cache, request_delay_s
    )
    hits = sum(1 for value in sampled if value is not None)
    _LOGGER.debug(
        "DEM lookup: %s of %s sampled points resolved (%s track points)",
        hits,
        len(indices),
        len(track),
    )
    return interpolate(len(track), indices, sampled)
