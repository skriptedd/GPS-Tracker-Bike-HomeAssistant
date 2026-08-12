"""Shared entity base class."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DEFAULT_NAME, DOMAIN, SIGNAL_UPDATE
from .coordinator import BikeTrackerCoordinator


class BikeTrackerEntity(Entity):
    """Base entity: shares one device and one update signal."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator: BikeTrackerCoordinator, key: str) -> None:
        self.coordinator = coordinator
        self._key = key
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
            name=DEFAULT_NAME,
            manufacturer="Bike Tracker",
            model="GPS trip recorder",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="homeassistant://config/integrations/integration/"
            + DOMAIN,
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_UPDATE, self.async_write_ha_state
            )
        )
