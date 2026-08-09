"""Turn GPX files into recorded trips.

Pure Python (no Home Assistant imports) so the whole import path can be
tested by round-tripping the exporter's own output back in.

Only *recorded* tracks can be imported: a trip needs timestamps to have a
duration, a speed and a moving time. Planned routes exported by Komoot or
BRouter carry coordinates but no ``<time>`` and are rejected with a clear
message rather than silently stored as a zero-second ride.
"""

from __future__ import annotations

import os
from collections.abc import Sequence

from .gpx import GpxError, GpxTrack, parse_gpx
from .tracker import GpsPoint, TrackerConfig, Trip, trip_from_points

GPX_SUFFIXES = (".gpx", ".GPX")

# Two trips this far apart at the start are treated as the same ride when
# checking for duplicates.
DUPLICATE_TOLERANCE_S = 120.0


def trip_from_gpx_track(
    track: GpxTrack, cfg: TrackerConfig, activity: str | None = None
) -> Trip:
    """Build a trip from one parsed <trk>."""
    if len(track.points) < 2:
        raise GpxError(f"Track '{track.name}' has fewer than two points")
    if not track.has_times:
        raise GpxError(
            f"Track '{track.name}' has no timestamps - it looks like a planned "
            "route, not a recorded ride"
        )

    points = [
        GpsPoint(ts=float(point.ts), lat=point.lat, lon=point.lon, alt=point.alt)
        for point in track.points
        if point.ts is not None
    ]
    points.sort(key=lambda point: point.ts)
    return trip_from_points(points, cfg, activity or track.activity)


def read_gpx_file(path: str) -> list[GpxTrack]:
    """Parse one .gpx file from disk. Blocking - call from an executor."""
    with open(path, encoding="utf-8-sig") as handle:
        return parse_gpx(handle.read())


def gpx_files_in(path: str) -> list[str]:
    """A single .gpx path, or every .gpx directly inside a directory."""
    if os.path.isdir(path):
        return sorted(
            os.path.join(path, name)
            for name in os.listdir(path)
            if name.endswith(GPX_SUFFIXES)
        )
    return [path]


def is_duplicate(
    trip: Trip,
    existing: Sequence[dict[str, object]],
    tolerance_s: float = DUPLICATE_TOLERANCE_S,
) -> bool:
    """True when one of ``existing`` is plainly the same ride.

    Overlapping in time is not enough on its own - a phone-recorded ride and
    the same ride exported from a bike computer should count as duplicates,
    but two different rides can never start within two minutes of each other.
    """
    for row in existing:
        started = float(row.get("started_at") or 0.0)
        if abs(started - trip.started_at) <= tolerance_s:
            return True
    return False
