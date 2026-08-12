#!/usr/bin/env python3
"""Fill the Bike Tracker database with a realistic set of demo rides.

Verifying the card needs history: a bar chart wants weeks of rides, segments
want the same stretch of road ridden several times. ``replay_track.py``
produces a single ride in real time, which is not enough - this writes a whole
season straight into ``bike_tracker.db``.

Run it **on the Home Assistant machine**, where the database lives:

    wget -O /tmp/seed.py https://raw.githubusercontent.com/skriptedd/GPS-Tracker-Bike-HomeAssistant/main/scripts/seed_demo_data.py
    python3 /tmp/seed.py --dry-run
    python3 /tmp/seed.py

Afterwards reload the integration (Settings -> Devices & services ->
Bike Tracker -> three dots -> Reload) so the statistics are recomputed.

Nothing is ever deleted. Every generated trip is marked with the note
``demo`` so it can be told apart from real rides:

    python3 /tmp/seed.py --remove      # deletes only trips noted "demo"
"""

from __future__ import annotations

import argparse
import math
import os
import random
import sys
from datetime import datetime, timedelta, timezone

DEFAULT_DB = "/config/bike_tracker.db"
DEFAULT_COMPONENT = "/config/custom_components/bike_tracker"

# Regensburg - override with --lat/--lon.
DEFAULT_LAT = 49.0134
DEFAULT_LON = 12.1016

POINT_INTERVAL_S = 10.0
DEMO_NOTE = "demo"

# Three routes that come back week after week, so segments have something to
# compare. (name, bearing in degrees, one-way distance in km, metres of climb)
ROUTES = [
    ("Donaurunde", 75.0, 11.0, 60.0),
    ("Hausberg", 200.0, 8.0, 240.0),
    ("Feierabendrunde", 310.0, 6.0, 35.0),
]


def load_component(path: str):
    """Import the integration's pure modules straight from the config dir.

    Reusing the real TripStore guarantees the demo rows match the schema the
    integration expects - no second, drifting copy of the table layout.
    """
    import importlib.util
    import types

    if not os.path.isdir(path):
        sys.exit(
            f"{path} not found. Pass --component if the integration lives "
            "somewhere else."
        )

    package = types.ModuleType("bt")
    package.__path__ = [path]
    package.__package__ = "bt"
    spec = importlib.util.spec_from_loader("bt", loader=None, is_package=True)
    spec.submodule_search_locations = [path]
    package.__spec__ = spec
    sys.modules["bt"] = package

    from bt.segments import match_segment, segment_from_track  # noqa: E402
    from bt.storage import TripStore  # noqa: E402
    from bt.tracker import GpsPoint, TrackerConfig, trip_from_points  # noqa: E402

    return {
        "TripStore": TripStore,
        "GpsPoint": GpsPoint,
        "TrackerConfig": TrackerConfig,
        "trip_from_points": trip_from_points,
        "segment_from_track": segment_from_track,
        "match_segment": match_segment,
    }


def ride_points(
    mod,
    start_ts: float,
    lat: float,
    lon: float,
    bearing_deg: float,
    distance_km: float,
    climb_m: float,
    speed_kmh: float,
    rng: random.Random,
):
    """An out-and-back ride: outbound climbing, return descending."""
    metres_per_step = (speed_kmh / 3.6) * POINT_INTERVAL_S
    steps_out = max(2, int((distance_km * 1000.0) / metres_per_step))
    bearing = math.radians(bearing_deg)
    lat_scale = 111_320.0
    lon_scale = 111_320.0 * math.cos(math.radians(lat))

    points = []
    altitude = 340.0
    ts = start_ts
    for direction, steps in ((1, steps_out), (-1, steps_out)):
        for step in range(steps):
            travelled = step * metres_per_step
            if direction < 0:
                travelled = steps_out * metres_per_step - travelled
            # A gentle curve, so the track is not a dead-straight line.
            curve = math.sin(travelled / (distance_km * 400.0)) * 0.25
            heading = bearing + curve
            north = math.cos(heading) * travelled
            east = math.sin(heading) * travelled

            progress = travelled / (steps_out * metres_per_step)
            altitude = 340.0 + climb_m * math.sin(progress * math.pi / 2.0)

            # A metre or two of GPS wobble keeps the elevation filter honest.
            points.append(
                mod["GpsPoint"](
                    ts=ts,
                    lat=lat + (north + rng.gauss(0, 1.5)) / lat_scale,
                    lon=lon + (east + rng.gauss(0, 1.5)) / lon_scale,
                    alt=altitude + rng.gauss(0, 2.0),
                    accuracy=rng.uniform(4.0, 12.0),
                    reported_speed_kmh=max(
                        0.0, speed_kmh + rng.gauss(0, 2.0)
                    ),
                )
            )
            ts += POINT_INTERVAL_S
    return points


def build_schedule(weeks: int, rng: random.Random):
    """(start timestamp, route, speed, activity) for every demo trip."""
    now = datetime.now(timezone.utc)
    plan = []
    for week in range(weeks, 0, -1):
        # Two or three rides a week, plus the odd walk.
        for _ in range(rng.randint(2, 3)):
            day = now - timedelta(
                days=week * 7 - rng.randint(0, 6), hours=rng.uniform(8, 19)
            )
            route = rng.choice(ROUTES)
            plan.append((day.timestamp(), route, rng.uniform(19.0, 27.5), "bike"))
        if rng.random() < 0.5:
            day = now - timedelta(days=week * 7 - rng.randint(0, 6), hours=17)
            plan.append(
                (day.timestamp(), ("Spaziergang", 120.0, 2.0, 15.0), 5.2, "walk")
            )

    # The loop above works in whole weeks back from today, so on a Monday or
    # Tuesday it can leave the current calendar week - and "today" - empty.
    # The statistics tiles would then read zero and look broken, which is
    # exactly what the demo data is supposed to disprove. Pin one ride to
    # today and one to yesterday.
    plan.append(((now - timedelta(hours=3)).timestamp(), ROUTES[0], 23.5, "bike"))
    plan.append(((now - timedelta(days=1, hours=5)).timestamp(), ROUTES[1], 21.0, "bike"))

    plan.sort(key=lambda entry: entry[0])
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--component", default=DEFAULT_COMPONENT)
    parser.add_argument("--weeks", type=int, default=6)
    parser.add_argument("--lat", type=float, default=DEFAULT_LAT)
    parser.add_argument("--lon", type=float, default=DEFAULT_LON)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--dry-run", action="store_true", help="show what would be written"
    )
    parser.add_argument(
        "--remove", action="store_true", help="delete the demo trips again"
    )
    parser.add_argument(
        "--status", action="store_true", help="what is actually in the database"
    )
    args = parser.parse_args()

    mod = load_component(args.component)
    rng = random.Random(args.seed)

    store = mod["TripStore"](args.db)
    store.connect()

    if args.status:
        import importlib

        period_bounds = importlib.import_module("bt.stats").period_bounds
        now = datetime.now()
        rows = store.list_trips(limit=100_000)
        demo = [r for r in rows if (r.get("note") or "") == DEMO_NOTE]
        print(f"Datenbank : {args.db}")
        print(f"Fahrten   : {len(rows)} gesamt, davon {len(demo)} Demofahrten")
        if rows:
            newest = datetime.fromtimestamp(max(float(r["started_at"]) for r in rows))
            print(f"Neueste   : {newest:%Y-%m-%d %H:%M}")
        print("Zeitraeume (nur Rad):")
        for period in ("today", "week", "month", "year", "total"):
            start, end = period_bounds(period, now)
            agg = store.aggregate(start, end, "bike")
            print(
                f"  {period:6} {agg['trips']:4.0f} Fahrten  "
                f"{agg['distance_m'] / 1000:8.1f} km"
            )
        store.close()
        return 0

    if args.remove:
        removed = 0
        for row in store.list_trips(limit=100_000):
            if (row.get("note") or "") == DEMO_NOTE:
                store.delete_trip(int(row["id"]))
                removed += 1
        store.close()
        print(f"{removed} demo trips deleted.")
        return 0

    cfg = mod["TrackerConfig"](min_distance_m=0, min_duration_s=0)
    plan = build_schedule(args.weeks, rng)
    print(f"{len(plan)} trips planned over {args.weeks} weeks -> {args.db}")

    if args.dry_run:
        for start_ts, route, speed, activity in plan:
            when = datetime.fromtimestamp(start_ts).strftime("%Y-%m-%d %H:%M")
            print(f"  {when}  {route[0]:<16} {2 * route[2]:5.1f} km  {speed:.0f} km/h  {activity}")
        store.close()
        return 0

    first_bike_track = None
    written = 0
    for start_ts, route, speed, activity in plan:
        _name, bearing, distance_km, climb = route
        points = ride_points(
            mod, start_ts, args.lat, args.lon, bearing, distance_km, climb, speed, rng
        )
        trip = mod["trip_from_points"](points, cfg, activity)
        trip_id = store.save_trip(trip, "demo-seeder", True)
        store.set_note(trip_id, DEMO_NOTE)
        written += 1
        if activity == "bike" and first_bike_track is None and route is ROUTES[1]:
            first_bike_track = [
                (float(p["ts"]), float(p["lat"]), float(p["lon"]))
                for p in store.get_track(trip_id)
            ]

    # One segment on the climb, then score every trip against it so the card
    # has best times to show.
    efforts = 0
    if first_bike_track and len(first_bike_track) > 60:
        cut = len(first_bike_track) // 2
        segment = mod["segment_from_track"](
            "Hausberg-Anstieg", first_bike_track, 10, cut - 10
        )
        segment.id = store.create_segment(segment)
        for row in store.list_trips(limit=100_000, activity="bike"):
            track = [
                (float(p["ts"]), float(p["lat"]), float(p["lon"]))
                for p in store.get_track(int(row["id"]))
            ]
            effort = mod["match_segment"](segment, track)
            if effort is not None:
                store.save_effort(segment.id, int(row["id"]), effort)
                efforts += 1

    totals = store.aggregate(activity="bike")
    store.close()

    print(f"{written} trips written, segment efforts: {efforts}")
    print(
        f"Total: {totals['trips']:.0f} bike trips, "
        f"{totals['distance_m'] / 1000:.1f} km, "
        f"{totals['elevation_gain_m']:.0f} m of climbing"
    )
    print("Now reload the integration so the sensors pick it up.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
