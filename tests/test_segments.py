"""Segment matching against synthetic tracks."""

from __future__ import annotations

from bt.segments import Segment, match_segment, segment_from_track

START_TS = 1_720_000_000.0
LAT = 49.0
LON_STEP = 0.001  # ~73 m at 49 deg N


def track(count: int, interval_s: float = 10.0, start_ts: float = START_TS):
    """A straight eastbound track: (ts, lat, lon) per point."""
    return [
        (start_ts + i * interval_s, LAT, 12.0 + i * LON_STEP) for i in range(count)
    ]


def segment_over(points, first: int, last: int, radius_m: float = 35.0) -> Segment:
    built = segment_from_track("Teststrecke", points, first, last, radius_m)
    built.id = 1
    return built


def test_matches_the_same_ride_it_was_built_from():
    points = track(20)
    segment = segment_over(points, 5, 15)

    effort = match_segment(segment, points)

    assert effort is not None
    assert effort.start_index == 5
    assert effort.end_index == 15
    assert effort.duration_s == 100.0


def test_matches_a_later_ride_over_the_same_road():
    definition = segment_over(track(20), 5, 15)
    # Same road, ridden twice as fast a week later.
    later = track(20, interval_s=5.0, start_ts=START_TS + 604_800)

    effort = match_segment(definition, later)

    assert effort is not None
    assert effort.duration_s == 50.0
    assert effort.avg_speed_kmh > 0


def test_no_match_on_a_completely_different_road():
    definition = segment_over(track(20), 5, 15)
    elsewhere = [(START_TS + i * 10.0, 52.5, 13.4 + i * LON_STEP) for i in range(20)]

    assert match_segment(definition, elsewhere) is None


def test_no_match_when_only_the_start_is_touched():
    points = track(20)
    definition = segment_over(points, 5, 15)

    assert match_segment(definition, points[:8]) is None


def test_detour_between_start_and_end_is_rejected():
    points = track(20)
    definition = segment_over(points, 5, 15)

    # Passes the start, wanders 3 km north and back, then reaches the end.
    detour = (
        points[:6]
        + [(START_TS + 60 + i * 10.0, LAT + 0.03, 12.006) for i in range(30)]
        + [(START_TS + 400 + i * 10.0, LAT, 12.0 + (10 + i) * LON_STEP)
           for i in range(6)]
    )

    assert match_segment(definition, detour) is None


def test_two_laps_report_the_faster_one():
    points = track(20)
    definition = segment_over(points, 5, 15)

    # Lap one at 10 s per point, lap two at 4 s per point.
    lap_one = track(20)
    lap_two = [
        (START_TS + 1000 + i * 4.0, LAT, 12.0 + i * LON_STEP) for i in range(20)
    ]

    effort = match_segment(definition, lap_one + lap_two)

    assert effort is not None
    assert effort.duration_s == 40.0


def test_segment_from_track_measures_its_own_length():
    points = track(20)

    segment = segment_from_track("Anstieg", points, 0, 10)

    # Ten hops of ~73 m.
    assert 700 < segment.length_m < 760
    assert segment.start_lon == 12.0
    assert segment.end_lon == 12.0 + 10 * LON_STEP


def test_segment_from_track_defaults_to_the_whole_track():
    points = track(11)

    segment = segment_from_track("Ganze Runde", points)

    assert segment.start_lon == points[0][2]
    assert segment.end_lon == points[-1][2]


def test_zero_length_segment_never_matches():
    definition = Segment(
        id=1,
        name="kaputt",
        start_lat=LAT,
        start_lon=12.0,
        end_lat=LAT,
        end_lon=12.0,
        length_m=0.0,
    )

    assert match_segment(definition, track(20)) is None
