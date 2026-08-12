"""Activity classification: walk vs. bike vs. car.

Heuristic, but deliberately based on features that separate the three modes
well in practice:

* ``p85`` - 85th percentile of the moving speed. Robust against both GPS
  spikes and traffic lights, and it is the single most discriminating feature.
* ``peak`` - 95th percentile of the moving speed. A bicycle can hit 60 km/h
  downhill, but it cannot sustain it; a car easily exceeds it.
* ``stop_ratio`` - share of time spent below the moving threshold. City car
  trips and bike trips both stop a lot, walking rarely does.

Everything is exposed as a pure function so it can be unit tested and, later,
swapped for a trained model without touching the rest of the integration.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .const import (
    ACTIVITY_BIKE,
    ACTIVITY_CAR,
    ACTIVITY_UNKNOWN,
    ACTIVITY_WALK,
    BIKE_MAX_P85,
    BIKE_MAX_PEAK,
    MOVING_SPEED_THRESHOLD_KMH,
    WALK_MAX_P85,
)
from .geo import percentile


@dataclass(slots=True)
class Classification:
    """Result of a classification run."""

    activity: str
    confidence: float
    features: dict[str, float]


def classify(
    speeds_kmh: Sequence[float],
    distance_m: float = 0.0,
    duration_s: float = 0.0,
) -> Classification:
    """Classify a finished trip from its per-sample speed series."""
    samples = [s for s in speeds_kmh if s is not None and s >= 0.0]
    if len(samples) < 3:
        return Classification(ACTIVITY_UNKNOWN, 0.0, {})

    moving = [s for s in samples if s >= MOVING_SPEED_THRESHOLD_KMH]
    if len(moving) < 3:
        return Classification(ACTIVITY_UNKNOWN, 0.0, {"stop_ratio": 1.0})

    p50 = percentile(moving, 50)
    p85 = percentile(moving, 85)
    peak = percentile(moving, 95)
    stop_ratio = 1.0 - (len(moving) / len(samples))
    avg = sum(moving) / len(moving)

    features = {
        "p50": round(p50, 2),
        "p85": round(p85, 2),
        "peak": round(peak, 2),
        "avg_moving": round(avg, 2),
        "stop_ratio": round(stop_ratio, 3),
        "distance_m": round(distance_m, 1),
        "duration_s": round(duration_s, 1),
    }

    # --- Walking --------------------------------------------------------
    if p85 <= WALK_MAX_P85 and peak < 15.0:
        margin = (WALK_MAX_P85 - p85) / WALK_MAX_P85
        return Classification(ACTIVITY_WALK, _confidence(margin), features)

    # --- Car ------------------------------------------------------------
    # Either sustained high speed, or a peak no bicycle reaches.
    if p85 > BIKE_MAX_P85 or peak > BIKE_MAX_PEAK:
        over = max(
            (p85 - BIKE_MAX_P85) / BIKE_MAX_P85,
            (peak - BIKE_MAX_PEAK) / BIKE_MAX_PEAK,
        )
        return Classification(ACTIVITY_CAR, _confidence(over * 2.0), features)

    # --- Bike -----------------------------------------------------------
    # Distance to both neighbouring class boundaries, normalised.
    lower = (p85 - WALK_MAX_P85) / WALK_MAX_P85
    upper = (BIKE_MAX_P85 - p85) / BIKE_MAX_P85
    margin = min(lower, upper)

    # A "bike" trip that never stops and sits right at the upper boundary is
    # more likely a car on a rural road - reduce confidence accordingly.
    if p85 > 30.0 and stop_ratio < 0.05:
        margin *= 0.4

    return Classification(ACTIVITY_BIKE, _confidence(margin), features)


def _confidence(margin: float) -> float:
    """Map a normalised distance-to-boundary onto a 0.5-0.99 confidence."""
    margin = max(0.0, min(1.0, margin))
    return round(0.5 + 0.49 * margin, 3)
