"""Diagnostics for Bike Tracker."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import BikeTrackerCoordinator


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry (no coordinates included)."""
    coordinator: BikeTrackerCoordinator = hass.data[DOMAIN][entry.entry_id]
    size = await hass.async_add_executor_job(coordinator.store.size_bytes)
    return {
        "options": {
            k: v for k, v in coordinator.options.items() if k != "source_entity"
        },
        "source_entity_domain": coordinator.source_entity.split(".")[0],
        "tracker": {
            "state": coordinator.tracker.state,
            "is_recording": coordinator.tracker.is_recording,
            "speed_kmh": coordinator.tracker.current_speed_kmh,
            "rejected_points": coordinator.tracker.rejected_points,
            "current_trip_points": (
                len(coordinator.tracker.trip.points)
                if coordinator.tracker.trip
                else 0
            ),
        },
        "statistics": coordinator.stats,
        "database_bytes": size,
    }
