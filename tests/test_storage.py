"""Tests for the SQLite store and the GPX exporter."""

import pathlib

from bt.gpx import build_gpx
from bt.storage import TripStore
from bt.tracker import TrackerConfig, TripTracker
from simulator import standstill, straight_track

T0 = 1_700_000_000.0
LAT, LON = 52.5, 13.4


def _recorded_trip():
    finished = []
    tracker = TripTracker(TrackerConfig(), on_trip_finished=finished.append)
    for point in straight_track(
        T0, LAT, LON, 20.0, 1200, altitude_start=50.0, altitude_rate_m_per_km=5.0
    ) + standstill(T0 + 1210, LAT, LON + 0.1, 400):
        tracker.add_point(point)
    tracker.tick(T0 + 99_999)
    assert finished
    return finished[0]


def _store(tmp_path: pathlib.Path) -> TripStore:
    store = TripStore(str(tmp_path / "test.db"))
    store.connect()
    return store


def test_save_and_read_back(tmp_path):
    store = _store(tmp_path)
    trip = _recorded_trip()
    trip_id = store.save_trip(trip, source_entity="device_tracker.phone")

    stored = store.get_trip(trip_id)
    assert stored is not None
    assert stored["activity"] == "bike"
    assert abs(stored["distance_m"] - trip.distance_m) < 1.0
    assert stored["point_count"] == len(trip.points)

    track = store.get_track(trip_id)
    assert len(track) == len(trip.points)
    assert track == sorted(track, key=lambda p: p["ts"])
    store.close()


def test_aggregate_and_daily(tmp_path):
    store = _store(tmp_path)
    trip = _recorded_trip()
    store.save_trip(trip)
    store.save_trip(_recorded_trip())

    totals = store.aggregate(activity="bike")
    assert totals["trips"] == 2
    assert totals["distance_m"] > 12_000
    assert totals["avg_speed_kmh"] > 10

    daily = store.daily_totals(T0 - 86400, T0 + 86400, "bike")
    assert len(daily) == 1
    assert daily[0]["trips"] == 2
    store.close()


def test_set_activity_and_delete(tmp_path):
    store = _store(tmp_path)
    trip_id = store.save_trip(_recorded_trip())

    assert store.set_activity(trip_id, "car")
    assert store.get_trip(trip_id)["activity"] == "car"
    assert store.aggregate(activity="bike")["trips"] == 0

    assert store.set_note(trip_id, "Regen")
    assert store.get_trip(trip_id)["note"] == "Regen"

    assert store.delete_trip(trip_id)
    assert store.get_trip(trip_id) is None
    assert store.get_track(trip_id) == []
    store.close()


def test_purge(tmp_path):
    store = _store(tmp_path)
    store.save_trip(_recorded_trip())
    # The synthetic trip is from 2023, so any retention window removes it.
    assert store.purge_older_than(30) == 1
    assert store.aggregate()["trips"] == 0
    assert store.purge_older_than(0) == 0
    store.close()


def test_gpx_export_is_wellformed(tmp_path):
    from xml.etree import ElementTree

    store = _store(tmp_path)
    trip_id = store.save_trip(_recorded_trip())
    xml = build_gpx(store.get_trip(trip_id), store.get_track(trip_id))

    root = ElementTree.fromstring(xml)
    ns = {"g": "http://www.topografix.com/GPX/1/1"}
    points = root.findall(".//g:trkpt", ns)
    assert len(points) > 50
    assert points[0].get("lat") is not None
    assert root.find(".//g:type", ns).text == "cycling"
    store.close()
