"""GPX 1.1 export and import.

The export is compatible with Strava, Komoot, Garmin and gpx.studio; the
import reads what those write back out. No Home Assistant imports, so both
directions are unit tested standalone.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from xml.etree import ElementTree
from xml.sax.saxutils import escape

ACTIVITY_GPX_TYPE = {
    "bike": "cycling",
    "walk": "walking",
    "car": "driving",
    "unknown": "other",
}

GPX_TYPE_ACTIVITY = {
    "cycling": "bike",
    "biking": "bike",
    "ride": "bike",
    "walking": "walk",
    "hiking": "walk",
    "running": "walk",
    "driving": "car",
}


class GpxError(Exception):
    """The file is not GPX, or holds nothing we can turn into a trip."""


def _iso(timestamp: float) -> str:
    return (
        datetime.fromtimestamp(float(timestamp), timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def build_gpx(trip: dict[str, Any], track: list[dict[str, Any]]) -> str:
    """Render one trip as a GPX document."""
    started = _iso(trip["started_at"])
    name = f"{trip.get('activity', 'trip').title()} {started[:10]}"
    gpx_type = ACTIVITY_GPX_TYPE.get(str(trip.get("activity")), "other")

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<gpx version="1.1" creator="Home Assistant Bike Tracker"',
        '     xmlns="http://www.topografix.com/GPX/1/1"',
        '     xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"',
        '     xsi:schemaLocation="http://www.topografix.com/GPX/1/1 '
        'http://www.topografix.com/GPX/1/1/gpx.xsd">',
        "  <metadata>",
        f"    <name>{escape(name)}</name>",
        f"    <time>{started}</time>",
        "  </metadata>",
        "  <trk>",
        f"    <name>{escape(name)}</name>",
        f"    <type>{gpx_type}</type>",
        "    <trkseg>",
    ]

    for point in track:
        lines.append(f'      <trkpt lat="{point["lat"]:.7f}" lon="{point["lon"]:.7f}">')
        if point.get("alt") is not None:
            lines.append(f"        <ele>{float(point['alt']):.1f}</ele>")
        lines.append(f"        <time>{_iso(point['ts'])}</time>")
        lines.append("      </trkpt>")

    lines.extend(["    </trkseg>", "  </trk>", "</gpx>", ""])
    return "\n".join(lines)


# --- import -------------------------------------------------------------


@dataclass(slots=True)
class GpxPoint:
    """One <trkpt>. ``ts`` is None when the file carries no timestamps."""

    lat: float
    lon: float
    ts: float | None = None
    alt: float | None = None


@dataclass(slots=True)
class GpxTrack:
    """One <trk>, with all its segments flattened into a single point list."""

    name: str
    points: list[GpxPoint] = field(default_factory=list)
    activity: str | None = None

    @property
    def has_times(self) -> bool:
        return all(point.ts is not None for point in self.points)


def _local_name(tag: str) -> str:
    """``{http://...}trkpt`` -> ``trkpt``."""
    return tag.rsplit("}", 1)[-1]


def _find_child(element: Any, name: str) -> Any | None:
    for child in element:
        if _local_name(child.tag) == name:
            return child
    return None


def _parse_time(text: str | None) -> float | None:
    if not text:
        return None
    value = text.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _parse_float(text: str | None) -> float | None:
    if text is None:
        return None
    try:
        return float(text.strip())
    except ValueError:
        return None


def parse_gpx(xml: str) -> list[GpxTrack]:
    """Read every <trk> of a GPX document.

    Namespace tolerant (GPX 1.0 and 1.1 use different ones, and plenty of
    exporters add their own). Track segments are merged into one point list -
    a pause in a recording is a gap in time, which the importer handles.
    """
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as err:
        raise GpxError(f"Not valid XML: {err}") from err

    if _local_name(root.tag) != "gpx":
        raise GpxError(f"Root element is <{_local_name(root.tag)}>, expected <gpx>")

    tracks: list[GpxTrack] = []
    for track_element in root:
        if _local_name(track_element.tag) != "trk":
            continue

        name_element = _find_child(track_element, "name")
        type_element = _find_child(track_element, "type")
        track = GpxTrack(
            name=(name_element.text or "").strip() if name_element is not None else "",
            activity=GPX_TYPE_ACTIVITY.get(
                (type_element.text or "").strip().lower()
                if type_element is not None and type_element.text
                else ""
            ),
        )

        for segment in track_element:
            if _local_name(segment.tag) != "trkseg":
                continue
            for point in segment:
                if _local_name(point.tag) != "trkpt":
                    continue
                lat = _parse_float(point.get("lat"))
                lon = _parse_float(point.get("lon"))
                if lat is None or lon is None:
                    continue
                elevation = _find_child(point, "ele")
                time_element = _find_child(point, "time")
                track.points.append(
                    GpxPoint(
                        lat=lat,
                        lon=lon,
                        ts=_parse_time(
                            time_element.text if time_element is not None else None
                        ),
                        alt=_parse_float(
                            elevation.text if elevation is not None else None
                        ),
                    )
                )

        if track.points:
            tracks.append(track)

    if not tracks:
        raise GpxError("The file contains no track points")
    return tracks
