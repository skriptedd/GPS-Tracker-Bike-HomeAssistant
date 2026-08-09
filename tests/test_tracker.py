"""End-to-end tests of the trip detection state machine."""

from bt.const import ACTIVITY_BIKE, ACTIVITY_WALK
from bt.tracker import GpsPoint, TrackerConfig, TripTracker
from simulator import standstill, straight_track

T0 = 1_700_000_000.0
LAT, LON = 52.5, 13.4


def run(points, config=None):
    finished, discarded = [], []
    tracker = TripTracker(
        config=config or TrackerConfig(),
        on_trip_finished=finished.append,
        on_trip_discarded=lambda trip, reason: discarded.append((trip, reason)),
    )
    for point in points:
        tracker.add_point(point)
    tracker.tick(points[-1].ts + 10_000)
    return tracker, finished, discarded


def test_detects_a_bike_ride():
    points = (
        standstill(T0, LAT, LON, 300)
        + straight_track(T0 + 310, LAT, LON, 20.0, 1200)
        + standstill(T0 + 1520, LAT, LON + 0.1, 400)
    )
    _, finished, _ = run(points)

    assert len(finished) == 1
    trip = finished[0]
    # 20 km/h for 20 minutes is ~6.7 km.
    assert 6000 < trip.distance_m < 7200
    assert trip.activity == ACTIVITY_BIKE
    assert trip.duration_s > 1000


def test_walking_is_not_a_bike_ride():
    points = straight_track(T0, LAT, LON, 5.0, 2400)
    _, finished, _ = run(points)
    # A walk is slower than the start threshold, so no trip opens at all.
    assert finished == []


def test_brisk_walk_is_classified_as_walk():
    config = TrackerConfig(start_speed_kmh=4.0, start_duration_s=30)
    points = straight_track(T0, LAT, LON, 6.0, 2400) + standstill(
        T0 + 2410, LAT, LON, 300
    )
    _, finished, _ = run(points, config)
    assert len(finished) == 1
    assert finished[0].activity == ACTIVITY_WALK


def test_short_hop_is_discarded():
    points = (
        straight_track(T0, LAT, LON, 18.0, 60)
        + standstill(T0 + 70, LAT, LON + 0.004, 300)
    )
    _, finished, discarded = run(points)
    assert finished == []
    assert discarded and discarded[0][1].startswith("too_short")


def test_stop_ends_the_trip_and_a_second_ride_is_separate():
    points = (
        straight_track(T0, LAT, LON, 22.0, 900)
        + standstill(T0 + 910, LAT, LON + 0.08, 900)
        + straight_track(T0 + 1820, LAT, LON + 0.08, 22.0, 900)
        + standstill(T0 + 2730, LAT, LON + 0.16, 600)
    )
    _, finished, _ = run(points)
    assert len(finished) == 2


def test_gps_teleport_is_rejected():
    points = straight_track(T0, LAT, LON, 20.0, 1200)
    points.insert(60, GpsPoint(ts=points[60].ts - 1, lat=48.1, lon=11.5, accuracy=5.0))
    tracker, finished, _ = run(points + standstill(T0 + 1210, LAT, LON + 0.1, 400))
    assert tracker.rejected_points >= 1
    assert len(finished) == 1
    assert finished[0].distance_m < 20_000


def test_inaccurate_fixes_are_dropped():
    points = straight_track(T0, LAT, LON, 20.0, 600, accuracy=250.0)
    tracker, finished, _ = run(points)
    assert finished == []
    assert tracker.rejected_points == len(points)


def test_elevation_gain_is_measured():
    points = straight_track(
        T0,
        LAT,
        LON,
        20.0,
        1800,
        altitude_start=100.0,
        altitude_rate_m_per_km=10.0,
    ) + standstill(T0 + 1810, LAT, LON + 0.15, 400)
    _, finished, _ = run(points)
    assert len(finished) == 1
    # 10 km at +10 m/km = ~100 m of climbing.
    assert 80 < finished[0].elevation_gain_m < 120
    assert finished[0].elevation_loss_m == 0.0


def test_trailing_standstill_is_trimmed():
    points = straight_track(T0, LAT, LON, 20.0, 1200) + standstill(
        T0 + 1210, LAT, LON + 0.1, 600
    )
    _, finished, _ = run(points)
    trip = finished[0]
    # The parked minutes at the end must not inflate the duration.
    assert trip.duration_s < 1400


def test_manual_start_and_stop():
    tracker = TripTracker()
    points = straight_track(T0, LAT, LON, 12.0, 300)
    tracker.add_point(points[0])
    tracker.force_start(points[0])
    assert tracker.is_recording
    for point in points[1:]:
        tracker.add_point(point)
    finished = []
    tracker._on_finished = finished.append
    tracker.force_stop()
    assert len(finished) == 1
    assert finished[0].manual is True


def test_discard_drops_the_trip():
    tracker, _, _ = run(straight_track(T0, LAT, LON, 20.0, 600))
    tracker.discard()
    assert tracker.trip is None
    assert not tracker.is_recording
