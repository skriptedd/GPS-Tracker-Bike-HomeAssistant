"""SQLite persistence for trips and track points.

Deliberately *not* the Home Assistant recorder: a recorded track is a few
thousand rows per ride and would bloat the recorder database and its purge
cycle. A dedicated file in the config directory keeps the data forever,
survives recorder purges, and is trivial to back up or delete.

All calls are synchronous sqlite3 and are expected to be executed from an
executor thread (see ``BikeTrackerStore`` wrappers in coordinator.py).
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from typing import Any

from .segments import Segment, SegmentEffort
from .tracker import Trip

_LOGGER = logging.getLogger(__name__)

# 2 added the segments / segment_efforts tables. Every statement below is
# "IF NOT EXISTS" and runs on each connect, so upgrading is just a restart.
SCHEMA_VERSION = 2

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS trips (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    uid                 TEXT NOT NULL UNIQUE,
    started_at          REAL NOT NULL,
    ended_at            REAL NOT NULL,
    activity            TEXT NOT NULL,
    activity_confidence REAL NOT NULL DEFAULT 0,
    auto_activity       TEXT,
    distance_m          REAL NOT NULL DEFAULT 0,
    duration_s          REAL NOT NULL DEFAULT 0,
    moving_time_s       REAL NOT NULL DEFAULT 0,
    avg_speed_kmh       REAL NOT NULL DEFAULT 0,
    avg_moving_kmh      REAL NOT NULL DEFAULT 0,
    max_speed_kmh       REAL NOT NULL DEFAULT 0,
    elevation_gain_m    REAL NOT NULL DEFAULT 0,
    elevation_loss_m    REAL NOT NULL DEFAULT 0,
    elevation_min_m     REAL,
    elevation_max_m     REAL,
    point_count         INTEGER NOT NULL DEFAULT 0,
    confirmed           INTEGER NOT NULL DEFAULT 1,
    manual              INTEGER NOT NULL DEFAULT 0,
    source_entity       TEXT,
    note                TEXT,
    created_at          REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS points (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    trip_id   INTEGER NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
    ts        REAL NOT NULL,
    lat       REAL NOT NULL,
    lon       REAL NOT NULL,
    alt       REAL,
    accuracy  REAL,
    speed_kmh REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS segments (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE,
    start_lat  REAL NOT NULL,
    start_lon  REAL NOT NULL,
    end_lat    REAL NOT NULL,
    end_lon    REAL NOT NULL,
    length_m   REAL NOT NULL DEFAULT 0,
    radius_m   REAL NOT NULL,
    activity   TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS segment_efforts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    segment_id    INTEGER NOT NULL REFERENCES segments(id) ON DELETE CASCADE,
    trip_id       INTEGER NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
    started_at    REAL NOT NULL,
    duration_s    REAL NOT NULL,
    distance_m    REAL NOT NULL,
    avg_speed_kmh REAL NOT NULL,
    UNIQUE(segment_id, trip_id)
);

CREATE INDEX IF NOT EXISTS idx_trips_started ON trips(started_at);
CREATE INDEX IF NOT EXISTS idx_trips_activity ON trips(activity, started_at);
CREATE INDEX IF NOT EXISTS idx_points_trip ON points(trip_id, ts);
CREATE INDEX IF NOT EXISTS idx_efforts_segment
    ON segment_efforts(segment_id, duration_s);
"""

TRIP_COLUMNS = (
    "id, uid, started_at, ended_at, activity, activity_confidence, auto_activity, "
    "distance_m, duration_s, moving_time_s, avg_speed_kmh, avg_moving_kmh, "
    "max_speed_kmh, elevation_gain_m, elevation_loss_m, elevation_min_m, "
    "elevation_max_m, point_count, confirmed, manual, source_entity, note, created_at"
)

# Same list minus the auto-increment primary key, used for INSERT.
INSERT_COLUMNS = TRIP_COLUMNS.split(", ", 1)[1]
INSERT_PLACEHOLDERS = ", ".join("?" * len(INSERT_COLUMNS.split(", ")))


class TripStore:
    """Thin synchronous wrapper around the SQLite database."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._conn: sqlite3.Connection | None = None

    # -- lifecycle -------------------------------------------------------

    def connect(self) -> None:
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA)
        self._conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
        self._conn.commit()
        _LOGGER.debug("Bike Tracker database ready at %s", self.path)

    def close(self) -> None:
        if self._conn is not None:
            self._conn.commit()
            self._conn.close()
            self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("TripStore is not connected")
        return self._conn

    # -- writes ----------------------------------------------------------

    def save_trip(
        self,
        trip: Trip,
        source_entity: str | None = None,
        confirmed: bool = True,
    ) -> int:
        cur = self.conn.execute(
            f"INSERT INTO trips ({INSERT_COLUMNS}) "
            f"VALUES ({INSERT_PLACEHOLDERS})",
            (
                trip.uid,
                trip.started_at,
                trip.ended_at,
                trip.activity,
                trip.activity_confidence,
                trip.activity,
                round(trip.distance_m, 2),
                round(trip.duration_s, 2),
                round(trip.moving_time_s, 2),
                round(trip.avg_speed_kmh, 2),
                round(trip.avg_moving_speed_kmh, 2),
                round(trip.max_speed_kmh, 2),
                trip.elevation_gain_m,
                trip.elevation_loss_m,
                trip.elevation_min_m,
                trip.elevation_max_m,
                len(trip.points),
                1 if confirmed else 0,
                1 if trip.manual else 0,
                source_entity,
                None,
                datetime.now(timezone.utc).timestamp(),
            ),
        )
        trip_id = int(cur.lastrowid or 0)
        self.conn.executemany(
            "INSERT INTO points (trip_id, ts, lat, lon, alt, accuracy, speed_kmh) "
            "VALUES (?,?,?,?,?,?,?)",
            [
                (
                    trip_id,
                    p.ts,
                    round(p.lat, 7),
                    round(p.lon, 7),
                    round(p.alt, 1) if p.alt is not None else None,
                    p.accuracy,
                    round(p.speed_kmh, 2),
                )
                for p in trip.points
            ],
        )
        self.conn.commit()
        return trip_id

    def set_activity(self, trip_id: int, activity: str) -> bool:
        cur = self.conn.execute(
            "UPDATE trips SET activity = ?, confirmed = 1, activity_confidence = 1.0 "
            "WHERE id = ?",
            (activity, trip_id),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def update_elevation(
        self,
        trip_id: int,
        gain_m: float,
        loss_m: float,
        min_m: float | None,
        max_m: float | None,
    ) -> bool:
        """Overwrite a trip's elevation figures (used after a DEM refresh)."""
        cur = self.conn.execute(
            "UPDATE trips SET elevation_gain_m = ?, elevation_loss_m = ?, "
            "elevation_min_m = ?, elevation_max_m = ? WHERE id = ?",
            (gain_m, loss_m, min_m, max_m, trip_id),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def update_point_altitudes(
        self, trip_id: int, altitudes: Iterable[float | None]
    ) -> int:
        """Replace the altitude of every track point, in recorded order."""
        ids = [
            int(row["id"])
            for row in self.conn.execute(
                "SELECT id FROM points WHERE trip_id = ? ORDER BY ts ASC", (trip_id,)
            )
        ]
        pairs = [
            (round(alt, 1) if alt is not None else None, point_id)
            for point_id, alt in zip(ids, altitudes, strict=False)
        ]
        self.conn.executemany("UPDATE points SET alt = ? WHERE id = ?", pairs)
        self.conn.commit()
        return len(pairs)

    def set_note(self, trip_id: int, note: str | None) -> bool:
        cur = self.conn.execute(
            "UPDATE trips SET note = ? WHERE id = ?", (note, trip_id)
        )
        self.conn.commit()
        return cur.rowcount > 0

    def confirm(self, trip_id: int) -> bool:
        cur = self.conn.execute(
            "UPDATE trips SET confirmed = 1 WHERE id = ?", (trip_id,)
        )
        self.conn.commit()
        return cur.rowcount > 0

    def delete_trip(self, trip_id: int) -> bool:
        cur = self.conn.execute("DELETE FROM trips WHERE id = ?", (trip_id,))
        self.conn.execute("DELETE FROM points WHERE trip_id = ?", (trip_id,))
        self.conn.commit()
        return cur.rowcount > 0

    def purge_older_than(self, days: int) -> int:
        if days <= 0:
            return 0
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).timestamp()
        ids = [
            row["id"]
            for row in self.conn.execute(
                "SELECT id FROM trips WHERE started_at < ?", (cutoff,)
            )
        ]
        for trip_id in ids:
            self.delete_trip(trip_id)
        return len(ids)

    # -- reads -----------------------------------------------------------

    def list_trips(
        self,
        limit: int = 50,
        offset: int = 0,
        activity: str | None = None,
        start: float | None = None,
        end: float | None = None,
    ) -> list[dict[str, Any]]:
        sql = f"SELECT {TRIP_COLUMNS} FROM trips WHERE 1=1"
        args: list[Any] = []
        if activity:
            sql += " AND activity = ?"
            args.append(activity)
        if start is not None:
            sql += " AND started_at >= ?"
            args.append(start)
        if end is not None:
            sql += " AND started_at < ?"
            args.append(end)
        sql += " ORDER BY started_at DESC LIMIT ? OFFSET ?"
        args.extend([limit, offset])
        return [dict(row) for row in self.conn.execute(sql, args)]

    def get_trip(self, trip_id: int) -> dict[str, Any] | None:
        row = self.conn.execute(
            f"SELECT {TRIP_COLUMNS} FROM trips WHERE id = ?", (trip_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_last_trip(self, activity: str | None = None) -> dict[str, Any] | None:
        trips = self.list_trips(limit=1, activity=activity)
        return trips[0] if trips else None

    def get_track(self, trip_id: int) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in self.conn.execute(
                "SELECT ts, lat, lon, alt, accuracy, speed_kmh FROM points "
                "WHERE trip_id = ? ORDER BY ts ASC",
                (trip_id,),
            )
        ]

    def aggregate(
        self,
        start: float | None = None,
        end: float | None = None,
        activity: str | None = None,
    ) -> dict[str, float]:
        sql = (
            "SELECT COUNT(*) AS trips, "
            "COALESCE(SUM(distance_m),0) AS distance_m, "
            "COALESCE(SUM(duration_s),0) AS duration_s, "
            "COALESCE(SUM(moving_time_s),0) AS moving_time_s, "
            "COALESCE(SUM(elevation_gain_m),0) AS elevation_gain_m, "
            "COALESCE(MAX(max_speed_kmh),0) AS max_speed_kmh, "
            "COALESCE(MAX(distance_m),0) AS longest_trip_m "
            "FROM trips WHERE 1=1"
        )
        args: list[Any] = []
        if activity:
            sql += " AND activity = ?"
            args.append(activity)
        if start is not None:
            sql += " AND started_at >= ?"
            args.append(start)
        if end is not None:
            sql += " AND started_at < ?"
            args.append(end)
        row = self.conn.execute(sql, args).fetchone()
        result = dict(row) if row else {}
        distance = float(result.get("distance_m") or 0.0)
        moving = float(result.get("moving_time_s") or 0.0)
        result["avg_speed_kmh"] = round((distance / moving) * 3.6, 2) if moving else 0.0
        return result

    def daily_totals(
        self, start: float, end: float, activity: str | None = None
    ) -> list[dict[str, Any]]:
        """Distance per calendar day - drives the bar chart in the card."""
        sql = (
            "SELECT date(started_at, 'unixepoch', 'localtime') AS day, "
            "COUNT(*) AS trips, SUM(distance_m) AS distance_m, "
            "SUM(moving_time_s) AS moving_time_s, "
            "SUM(elevation_gain_m) AS elevation_gain_m "
            "FROM trips WHERE started_at >= ? AND started_at < ?"
        )
        args: list[Any] = [start, end]
        if activity:
            sql += " AND activity = ?"
            args.append(activity)
        sql += " GROUP BY day ORDER BY day ASC"
        return [dict(row) for row in self.conn.execute(sql, args)]

    def counts_by_activity(self) -> dict[str, int]:
        return {
            row["activity"]: row["n"]
            for row in self.conn.execute(
                "SELECT activity, COUNT(*) AS n FROM trips GROUP BY activity"
            )
        }

    def unconfirmed(self, limit: int = 20) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in self.conn.execute(
                f"SELECT {TRIP_COLUMNS} FROM trips WHERE confirmed = 0 "
                "ORDER BY started_at DESC LIMIT ?",
                (limit,),
            )
        ]

    def size_bytes(self) -> int:
        row = self.conn.execute(
            "SELECT page_count * page_size AS size FROM pragma_page_count(), "
            "pragma_page_size()"
        ).fetchone()
        return int(row["size"]) if row else 0

    def iter_all_trip_ids(self) -> Iterable[int]:
        for row in self.conn.execute("SELECT id FROM trips ORDER BY started_at"):
            yield int(row["id"])

    def find_overlapping(
        self, started_at: float, ended_at: float
    ) -> list[dict[str, Any]]:
        """Trips whose time range overlaps the given one.

        Used by the GPX import to notice that a file has already been imported
        (or that it duplicates a ride the tracker recorded itself).
        """
        return [
            dict(row)
            for row in self.conn.execute(
                f"SELECT {TRIP_COLUMNS} FROM trips "
                "WHERE started_at < ? AND ended_at > ? ORDER BY started_at",
                (ended_at, started_at),
            )
        ]

    # -- segments --------------------------------------------------------

    def create_segment(self, segment: Segment) -> int:
        cur = self.conn.execute(
            "INSERT INTO segments (name, start_lat, start_lon, end_lat, end_lon, "
            "length_m, radius_m, activity, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                segment.name,
                round(segment.start_lat, 7),
                round(segment.start_lon, 7),
                round(segment.end_lat, 7),
                round(segment.end_lon, 7),
                round(segment.length_m, 1),
                segment.radius_m,
                segment.activity,
                datetime.now(timezone.utc).timestamp(),
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid or 0)

    def delete_segment(self, segment_id: int) -> bool:
        cur = self.conn.execute("DELETE FROM segments WHERE id = ?", (segment_id,))
        self.conn.execute(
            "DELETE FROM segment_efforts WHERE segment_id = ?", (segment_id,)
        )
        self.conn.commit()
        return cur.rowcount > 0

    def list_segments(self) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in self.conn.execute("SELECT * FROM segments ORDER BY name")
        ]

    def get_segment(self, segment_id: int) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM segments WHERE id = ?", (segment_id,)
        ).fetchone()
        return dict(row) if row else None

    def save_effort(
        self, segment_id: int, trip_id: int, effort: SegmentEffort
    ) -> int:
        """Store one traversal. Re-running the match updates it in place."""
        cur = self.conn.execute(
            "INSERT INTO segment_efforts "
            "(segment_id, trip_id, started_at, duration_s, distance_m, avg_speed_kmh) "
            "VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(segment_id, trip_id) DO UPDATE SET "
            "started_at = excluded.started_at, duration_s = excluded.duration_s, "
            "distance_m = excluded.distance_m, avg_speed_kmh = excluded.avg_speed_kmh",
            (
                segment_id,
                trip_id,
                effort.started_at,
                effort.duration_s,
                effort.distance_m,
                effort.avg_speed_kmh,
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid or 0)

    def list_efforts(self, segment_id: int, limit: int = 50) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in self.conn.execute(
                "SELECT * FROM segment_efforts WHERE segment_id = ? "
                "ORDER BY started_at DESC LIMIT ?",
                (segment_id, limit),
            )
        ]

    def best_effort(self, segment_id: int) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM segment_efforts WHERE segment_id = ? "
            "ORDER BY duration_s ASC LIMIT 1",
            (segment_id,),
        ).fetchone()
        return dict(row) if row else None

    def segments_with_stats(self) -> list[dict[str, Any]]:
        """Segments plus effort count, personal best and most recent effort."""
        out: list[dict[str, Any]] = []
        for segment in self.list_segments():
            efforts = self.list_efforts(int(segment["id"]), limit=1)
            best = self.best_effort(int(segment["id"]))
            count = self.conn.execute(
                "SELECT COUNT(*) AS n FROM segment_efforts WHERE segment_id = ?",
                (segment["id"],),
            ).fetchone()
            out.append(
                {
                    **segment,
                    "effort_count": int(count["n"]) if count else 0,
                    "best": best,
                    "latest": efforts[0] if efforts else None,
                }
            )
        return out
