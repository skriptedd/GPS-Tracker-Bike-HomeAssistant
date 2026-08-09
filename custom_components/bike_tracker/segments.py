"""Segment matching - "how fast was I on that climb this time?"

A segment is a named stretch of road defined by a start point, an end point
and the distance between them along the track it was created from. Every trip
is checked against every segment: if the track passes close to the start and
later close to the end, and the distance covered in between is plausible for
that segment, the elapsed time becomes an *effort*. The fastest effort is the
personal best.

Pure Python, no Home Assistant imports, so the matching can be replayed
against synthetic tracks in the test suite.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .const import (
    ACTIVITY_BIKE,
    DEFAULT_SEGMENT_RADIUS_M,
    SEGMENT_MAX_LENGTH_FACTOR,
)
from .geo import haversine, speed_kmh

# A track point as handed to the matcher: (timestamp, latitude, longitude).
TrackPoint = tuple[float, float, float]


@dataclass(slots=True)
class Segment:
    """A named stretch of road to compare rides on."""

    id: int
    name: str
    start_lat: float
    start_lon: float
    end_lat: float
    end_lon: float
    length_m: float
    radius_m: float = DEFAULT_SEGMENT_RADIUS_M
    activity: str = ACTIVITY_BIKE


@dataclass(slots=True)
class SegmentEffort:
    """One traversal of a segment."""

    segment_id: int
    started_at: float
    ended_at: float
    duration_s: float
    distance_m: float
    avg_speed_kmh: float
    start_index: int
    end_index: int


def _proximity_runs(
    track: Sequence[TrackPoint], lat: float, lon: float, radius_m: float
) -> list[int]:
    """Indices where the track is closest to a point, one per approach.

    Consecutive points inside the radius belong to the same approach; only the
    single closest one is returned, so riding through once yields one index.
    """
    hits: list[int] = []
    run_best_index: int | None = None
    run_best_distance = float("inf")

    for index, (_ts, point_lat, point_lon) in enumerate(track):
        distance = haversine(point_lat, point_lon, lat, lon)
        if distance <= radius_m:
            if run_best_index is None or distance < run_best_distance:
                run_best_index = index
                run_best_distance = distance
        elif run_best_index is not None:
            hits.append(run_best_index)
            run_best_index = None
            run_best_distance = float("inf")

    if run_best_index is not None:
        hits.append(run_best_index)
    return hits


def _travelled(track: Sequence[TrackPoint], first: int, last: int) -> float:
    """Distance along the track between two indices, in metres."""
    total = 0.0
    for index in range(first + 1, last + 1):
        _ts, lat, lon = track[index]
        _prev_ts, prev_lat, prev_lon = track[index - 1]
        total += haversine(prev_lat, prev_lon, lat, lon)
    return total


def match_segment(
    segment: Segment, track: Sequence[TrackPoint]
) -> SegmentEffort | None:
    """Fastest traversal of ``segment`` inside ``track``, if any.

    Rejects matches whose travelled distance is implausible for the segment -
    that filters out "passed the start, rode somewhere else, came back past the
    end an hour later".
    """
    if len(track) < 2 or segment.length_m <= 0:
        return None

    starts = _proximity_runs(
        track, segment.start_lat, segment.start_lon, segment.radius_m
    )
    if not starts:
        return None
    ends = _proximity_runs(track, segment.end_lat, segment.end_lon, segment.radius_m)
    if not ends:
        return None

    min_length = segment.length_m / SEGMENT_MAX_LENGTH_FACTOR
    max_length = segment.length_m * SEGMENT_MAX_LENGTH_FACTOR

    best: SegmentEffort | None = None
    for start_index in starts:
        for end_index in ends:
            if end_index <= start_index:
                continue
            distance = _travelled(track, start_index, end_index)
            if not min_length <= distance <= max_length:
                continue
            duration = track[end_index][0] - track[start_index][0]
            if duration <= 0:
                continue
            effort = SegmentEffort(
                segment_id=segment.id,
                started_at=track[start_index][0],
                ended_at=track[end_index][0],
                duration_s=round(duration, 1),
                distance_m=round(distance, 1),
                avg_speed_kmh=round(speed_kmh(distance, duration), 2),
                start_index=start_index,
                end_index=end_index,
            )
            if best is None or effort.duration_s < best.duration_s:
                best = effort
            # The first end point after this start is the shortest candidate;
            # a later one can only be longer.
            break

    return best


def segment_from_track(
    name: str,
    track: Sequence[TrackPoint],
    start_index: int = 0,
    end_index: int | None = None,
    radius_m: float = DEFAULT_SEGMENT_RADIUS_M,
    activity: str = ACTIVITY_BIKE,
) -> Segment:
    """Build a segment definition out of a slice of an existing track."""
    if len(track) < 2:
        raise ValueError("A segment needs at least two track points")

    last = len(track) - 1 if end_index is None else end_index
    start_index = max(0, min(start_index, last - 1)) if last > 0 else 0
    last = max(start_index + 1, min(last, len(track) - 1))

    return Segment(
        id=0,
        name=name,
        start_lat=track[start_index][1],
        start_lon=track[start_index][2],
        end_lat=track[last][1],
        end_lon=track[last][2],
        length_m=round(_travelled(track, start_index, last), 1),
        radius_m=radius_m,
        activity=activity,
    )
