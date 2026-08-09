"""Binary sensors for Bike Tracker."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import BikeTrackerCoordinator
from .entity import BikeTrackerEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the binary sensor platform."""
    coordinator: BikeTrackerCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([BikeRidingSensor(coordinator)])


class BikeRidingSensor(BikeTrackerEntity, BinarySensorEntity):
    """On while a trip is being recorded."""

    _attr_device_class = BinarySensorDeviceClass.MOVING
    _attr_icon = "mdi:bike-fast"

    def __init__(self, coordinator: BikeTrackerCoordinator) -> None:
        super().__init__(coordinator, "recording")

    @property
    def is_on(self) -> bool:
        return self.coordinator.tracker.is_recording

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        tracker = self.coordinator.tracker
        return {
            "state_machine": tracker.state,
            "speed_kmh": tracker.current_speed_kmh,
            "rejected_points": tracker.rejected_points,
            "source_entity": self.coordinator.source_entity,
        }
