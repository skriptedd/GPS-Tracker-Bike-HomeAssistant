"""Constants for the Bike Tracker integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "bike_tracker"
PLATFORMS: Final = ["sensor", "binary_sensor"]

DEFAULT_NAME: Final = "Bike Tracker"
DB_FILENAME: Final = "bike_tracker.db"

# --- Configuration keys -------------------------------------------------
CONF_SOURCE_ENTITY: Final = "source_entity"
CONF_MAX_ACCURACY: Final = "max_accuracy_m"
CONF_START_SPEED: Final = "start_speed_kmh"
CONF_START_DURATION: Final = "start_duration_s"
CONF_STOP_SPEED: Final = "stop_speed_kmh"
CONF_STOP_DURATION: Final = "stop_duration_s"
CONF_STALE_TIMEOUT: Final = "stale_timeout_s"
CONF_MIN_DISTANCE: Final = "min_trip_distance_m"
CONF_MIN_DURATION: Final = "min_trip_duration_s"
CONF_ELEVATION_THRESHOLD: Final = "elevation_threshold_m"
CONF_ELEVATION_SOURCE: Final = "elevation_source"
CONF_ELEVATION_URL: Final = "elevation_url"
CONF_TRACK_ALL_ACTIVITIES: Final = "track_all_activities"
CONF_REQUIRE_CONFIRMATION: Final = "require_confirmation"
CONF_RETENTION_DAYS: Final = "retention_days"
CONF_ROUTING_URL: Final = "routing_url"

# --- Defaults -----------------------------------------------------------
# Chosen for the Home Assistant companion app in "high accuracy" mode
# (one location update every 5-30 s).
DEFAULT_MAX_ACCURACY: Final = 50.0          # metres; worse fixes are dropped
DEFAULT_START_SPEED: Final = 7.0            # km/h; faster than a brisk walk
DEFAULT_START_DURATION: Final = 45.0        # s above start speed to open a trip
DEFAULT_STOP_SPEED: Final = 3.0             # km/h
DEFAULT_STOP_DURATION: Final = 150.0        # s below stop speed to close a trip
DEFAULT_STALE_TIMEOUT: Final = 600.0        # s without any fix -> close trip
DEFAULT_MIN_DISTANCE: Final = 400.0         # m; shorter trips are discarded
DEFAULT_MIN_DURATION: Final = 120.0         # s
DEFAULT_ELEVATION_THRESHOLD: Final = 3.0    # m; ignores GPS altitude noise
DEFAULT_RETENTION_DAYS: Final = 0           # 0 = keep forever
DEFAULT_ROUTING_URL: Final = "https://router.project-osrm.org"
# EU-DEM 25 m covers all of Europe. The public instance allows 1000 calls/day,
# which is plenty for a few rides; self-host it for heavy use.
DEFAULT_ELEVATION_URL: Final = "https://api.opentopodata.org/v1/eudem25m"

ELEVATION_SOURCE_GPS: Final = "gps"
ELEVATION_SOURCE_DEM: Final = "dem"
ELEVATION_SOURCE_NONE: Final = "none"
ELEVATION_SOURCES: Final = [
    ELEVATION_SOURCE_GPS,
    ELEVATION_SOURCE_DEM,
    ELEVATION_SOURCE_NONE,
]

# --- Physical sanity limits ---------------------------------------------
MAX_PLAUSIBLE_SPEED_KMH: Final = 200.0
MIN_SEGMENT_SECONDS: Final = 0.5
SPEED_SMOOTHING_WINDOW: Final = 5
ALTITUDE_MEDIAN_WINDOW: Final = 5

# --- Activities ---------------------------------------------------------
ACTIVITY_WALK: Final = "walk"
ACTIVITY_BIKE: Final = "bike"
ACTIVITY_CAR: Final = "car"
ACTIVITY_UNKNOWN: Final = "unknown"
ACTIVITIES: Final = [ACTIVITY_WALK, ACTIVITY_BIKE, ACTIVITY_CAR, ACTIVITY_UNKNOWN]

# Classification thresholds (km/h). p85 = 85th percentile of moving speed.
WALK_MAX_P85: Final = 8.5
BIKE_MAX_P85: Final = 38.0
BIKE_MAX_PEAK: Final = 65.0
CAR_MIN_P85: Final = 38.0

MOVING_SPEED_THRESHOLD_KMH: Final = 2.0

# --- Trip states --------------------------------------------------------
STATE_IDLE: Final = "idle"
STATE_CANDIDATE: Final = "candidate"
STATE_ACTIVE: Final = "active"

# --- Events / services --------------------------------------------------
EVENT_TRIP_STARTED: Final = f"{DOMAIN}_trip_started"
EVENT_TRIP_FINISHED: Final = f"{DOMAIN}_trip_finished"
EVENT_TRIP_DISCARDED: Final = f"{DOMAIN}_trip_discarded"
EVENT_ROUTE_PLANNED: Final = f"{DOMAIN}_route_planned"
EVENT_SEGMENT_MATCHED: Final = f"{DOMAIN}_segment_matched"
EVENT_SEGMENT_RECORD: Final = f"{DOMAIN}_segment_record"

SERVICE_START_TRIP: Final = "start_trip"
SERVICE_STOP_TRIP: Final = "stop_trip"
SERVICE_DISCARD_TRIP: Final = "discard_trip"
SERVICE_SET_ACTIVITY: Final = "set_activity"
SERVICE_DELETE_TRIP: Final = "delete_trip"
SERVICE_EXPORT_GPX: Final = "export_gpx"
SERVICE_IMPORT_GPX: Final = "import_gpx"
SERVICE_PLAN_ROUTE: Final = "plan_route"
SERVICE_PURGE: Final = "purge"
SERVICE_REFRESH_ELEVATION: Final = "refresh_elevation"
SERVICE_CREATE_SEGMENT: Final = "create_segment"
SERVICE_DELETE_SEGMENT: Final = "delete_segment"
SERVICE_RESCAN_SEGMENTS: Final = "rescan_segments"

# --- Segments -----------------------------------------------------------
# How close the track has to come to a segment's start/end to count as a
# match. 35 m is roughly one road width plus GPS error.
DEFAULT_SEGMENT_RADIUS_M: Final = 35.0
# A matched segment must be within this factor of the segment's own length,
# which rejects "passed the start and much later the end by another route".
SEGMENT_MAX_LENGTH_FACTOR: Final = 1.35

SIGNAL_UPDATE: Final = f"{DOMAIN}_update"

PERIOD_TODAY: Final = "today"
PERIOD_WEEK: Final = "week"
PERIOD_MONTH: Final = "month"
PERIOD_YEAR: Final = "year"
PERIOD_TOTAL: Final = "total"
PERIODS: Final = [PERIOD_TODAY, PERIOD_WEEK, PERIOD_MONTH, PERIOD_YEAR, PERIOD_TOTAL]
