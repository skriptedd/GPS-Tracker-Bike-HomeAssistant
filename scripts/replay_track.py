#!/usr/bin/env python3
"""Replay a synthetic bike ride into Home Assistant.

Feeds GPS fixes into a ``device_tracker`` entity over the REST API so the whole
detection pipeline - trip start, classification, statistics, map - can be
verified without leaving the desk.

The tracker timestamps every fix with the entity's ``last_updated``, so the
replay necessarily runs in real time: a four-minute ride takes four minutes.
That is long enough to clear the defaults (45 s above start speed, 120 s
minimum duration, 400 m minimum distance).

Usage
-----
    export BIKE_TRACKER_TOKEN=<long-lived access token>
    python scripts/replay_track.py --url http://homeassistant.local:9080

Create the token under your Home Assistant profile, at the very bottom:
"Long-lived access tokens" -> "Create token". The script never stores it.

Run it once *before* adding the integration, so the entity exists and can be
picked in the config flow.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import urllib.error
import urllib.request

EARTH_LAT_M = 111_320.0
# Regensburg city centre - overwrite with --lat/--lon.
DEFAULT_LAT = 49.0134
DEFAULT_LON = 12.1016


def build_ride(
    lat: float,
    lon: float,
    speed_kmh: float,
    minutes: float,
    interval_s: float,
    climb_m: float,
) -> list[dict[str, float]]:
    """A straight eastbound ride with a steady climb, sampled every interval."""
    steps = max(1, int((minutes * 60.0) / interval_s))
    metres_per_step = (speed_kmh / 3.6) * interval_s
    lon_scale = EARTH_LAT_M * math.cos(math.radians(lat))

    fixes = []
    current_lon = lon
    altitude = 340.0
    for step in range(steps + 1):
        fixes.append(
            {
                "latitude": round(lat, 7),
                "longitude": round(current_lon, 7),
                "gps_accuracy": 8,
                "altitude": round(altitude, 1),
                # The companion app reports speed in m/s.
                "speed": round(speed_kmh / 3.6, 2),
            }
        )
        current_lon += metres_per_step / lon_scale
        altitude += climb_m / steps
    return fixes


TOKEN_HOWTO = """Create one under Profile -> bottom of the page -> "Long-lived
access tokens" -> "Create token", then export the whole string. It starts with
eyJ and is several hundred characters long:

    export BIKE_TRACKER_TOKEN=eyJhbGciOiJIUzI1NiIsInR5cCI6...

A literal "eyJ..." is a placeholder, not a token."""

TOKEN_HELP = "Home Assistant rejected the token (HTTP 401).\n\n" + TOKEN_HOWTO
TOKEN_MISSING = "BIKE_TRACKER_TOKEN is not set.\n\n" + TOKEN_HOWTO
TOKEN_PLACEHOLDER = (
    "BIKE_TRACKER_TOKEN looks like the placeholder from the documentation, "
    "not a real token.\n\n" + TOKEN_HOWTO
)


def _fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(1)


def read_state(url: str, token: str, entity_id: str) -> dict | None:
    """Current state of the entity, or None if it does not exist yet."""
    request = urllib.request.Request(
        f"{url.rstrip('/')}/api/states/{entity_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as err:
        if err.code == 404:
            return None
        if err.code == 401:
            _fail(TOKEN_HELP)
        _fail(f"Home Assistant answered HTTP {err.code} for {entity_id}.")
    except urllib.error.URLError as err:
        _fail(f"Cannot reach {url}: {err.reason}")
    return None


def post_state(
    url: str,
    token: str,
    entity_id: str,
    attributes: dict[str, float],
    state: str,
    friendly_name: str,
) -> None:
    payload = json.dumps(
        {
            # Keep whatever the entity already reports. Replaying into a real
            # phone tracker with a hard-coded "not_home" would flip presence
            # and set off every away automation in the house.
            "state": state,
            "attributes": {
                "source_type": "gps",
                "friendly_name": friendly_name,
                **attributes,
            },
        }
    ).encode("utf-8")

    request = urllib.request.Request(
        f"{url.rstrip('/')}/api/states/{entity_id}",
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        if response.status not in (200, 201):
            raise RuntimeError(f"Home Assistant answered HTTP {response.status}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="e.g. http://homeassistant.local:9080")
    parser.add_argument("--entity", default="device_tracker.bike_test")
    parser.add_argument("--minutes", type=float, default=4.0)
    parser.add_argument("--speed", type=float, default=22.0, help="km/h")
    parser.add_argument("--interval", type=float, default=5.0, help="seconds per fix")
    parser.add_argument("--lat", type=float, default=DEFAULT_LAT)
    parser.add_argument("--lon", type=float, default=DEFAULT_LON)
    parser.add_argument("--climb", type=float, default=60.0, help="metres of ascent")
    parser.add_argument(
        "--state",
        help=(
            "state to write. Defaults to whatever the entity currently "
            "reports, so replaying into a real phone tracker does not flip "
            "presence and trigger away automations."
        ),
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="print the fixes, send nothing"
    )
    args = parser.parse_args()

    token = os.environ.get("BIKE_TRACKER_TOKEN", "").strip()
    if not args.dry_run:
        if not token:
            _fail(TOKEN_MISSING)
        # Catch the copied-the-example mistake before sending anything.
        if token.endswith("...") or len(token) < 50:
            _fail(TOKEN_PLACEHOLDER)

    fixes = build_ride(
        args.lat, args.lon, args.speed, args.minutes, args.interval, args.climb
    )
    total_s = len(fixes) * args.interval
    print(
        f"{len(fixes)} fixes, {args.speed:.0f} km/h, "
        f"{(args.speed / 3.6) * total_s / 1000:.2f} km, "
        f"{args.climb:.0f} m of climbing - takes about {total_s / 60:.1f} minutes."
    )

    if args.dry_run:
        for fix in fixes:
            print(fix)
        return 0

    existing = read_state(args.url, token, args.entity)
    state = args.state or (existing or {}).get("state") or "not_home"
    friendly = ((existing or {}).get("attributes") or {}).get(
        "friendly_name", "Bike Tracker Testgerät"
    )
    if existing is not None:
        print(f"Replaying into the existing entity, keeping state '{state}'.")

    for index, fix in enumerate(fixes, start=1):
        try:
            post_state(args.url, token, args.entity, fix, state, friendly)
        except urllib.error.HTTPError as err:
            print("", file=sys.stderr)
            _fail(TOKEN_HELP if err.code == 401 else f"Fix {index}: HTTP {err.code}")
        except (urllib.error.URLError, RuntimeError) as err:
            print(f"\nFix {index} failed: {err}", file=sys.stderr)
            return 1
        print(f"\r  fix {index}/{len(fixes)}", end="", flush=True)
        if index < len(fixes):
            time.sleep(args.interval)

    print("\nDone. Give it up to stop_duration (default 150 s) to close the trip,")
    print("or call bike_tracker.stop_trip to finish it right away.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
