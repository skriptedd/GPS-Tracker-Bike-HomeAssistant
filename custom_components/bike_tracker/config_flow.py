"""Config and options flow for Bike Tracker."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_ELEVATION_SOURCE,
    CONF_ELEVATION_THRESHOLD,
    CONF_ELEVATION_URL,
    CONF_MAX_ACCURACY,
    CONF_MIN_DISTANCE,
    CONF_MIN_DURATION,
    CONF_REQUIRE_CONFIRMATION,
    CONF_RETENTION_DAYS,
    CONF_ROUTING_URL,
    CONF_SOURCE_ENTITY,
    CONF_STALE_TIMEOUT,
    CONF_START_DURATION,
    CONF_START_SPEED,
    CONF_STOP_DURATION,
    CONF_STOP_SPEED,
    CONF_TRACK_ALL_ACTIVITIES,
    DEFAULT_ELEVATION_THRESHOLD,
    DEFAULT_ELEVATION_URL,
    DEFAULT_MAX_ACCURACY,
    DEFAULT_MIN_DISTANCE,
    DEFAULT_MIN_DURATION,
    DEFAULT_NAME,
    DEFAULT_RETENTION_DAYS,
    DEFAULT_ROUTING_URL,
    DEFAULT_STALE_TIMEOUT,
    DEFAULT_START_DURATION,
    DEFAULT_START_SPEED,
    DEFAULT_STOP_DURATION,
    DEFAULT_STOP_SPEED,
    DOMAIN,
    ELEVATION_SOURCE_GPS,
    ELEVATION_SOURCES,
)


def _number(minimum: float, maximum: float, step: float, unit: str | None = None):
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=minimum,
            max=maximum,
            step=step,
            unit_of_measurement=unit,
            mode=selector.NumberSelectorMode.BOX,
        )
    )


def _options_schema(current: dict[str, Any]) -> vol.Schema:
    def get(key: str, default: Any) -> Any:
        return current.get(key, default)

    return vol.Schema(
        {
            vol.Required(
                CONF_START_SPEED, default=get(CONF_START_SPEED, DEFAULT_START_SPEED)
            ): _number(1, 60, 0.5, "km/h"),
            vol.Required(
                CONF_START_DURATION,
                default=get(CONF_START_DURATION, DEFAULT_START_DURATION),
            ): _number(5, 600, 5, "s"),
            vol.Required(
                CONF_STOP_SPEED, default=get(CONF_STOP_SPEED, DEFAULT_STOP_SPEED)
            ): _number(0, 30, 0.5, "km/h"),
            vol.Required(
                CONF_STOP_DURATION,
                default=get(CONF_STOP_DURATION, DEFAULT_STOP_DURATION),
            ): _number(15, 1800, 15, "s"),
            vol.Required(
                CONF_STALE_TIMEOUT,
                default=get(CONF_STALE_TIMEOUT, DEFAULT_STALE_TIMEOUT),
            ): _number(60, 3600, 30, "s"),
            vol.Required(
                CONF_MAX_ACCURACY, default=get(CONF_MAX_ACCURACY, DEFAULT_MAX_ACCURACY)
            ): _number(0, 500, 5, "m"),
            vol.Required(
                CONF_MIN_DISTANCE, default=get(CONF_MIN_DISTANCE, DEFAULT_MIN_DISTANCE)
            ): _number(0, 10000, 50, "m"),
            vol.Required(
                CONF_MIN_DURATION, default=get(CONF_MIN_DURATION, DEFAULT_MIN_DURATION)
            ): _number(0, 3600, 15, "s"),
            vol.Required(
                CONF_ELEVATION_SOURCE,
                default=get(CONF_ELEVATION_SOURCE, ELEVATION_SOURCE_GPS),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=ELEVATION_SOURCES,
                    translation_key="elevation_source",
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(
                CONF_ELEVATION_URL,
                default=get(CONF_ELEVATION_URL, DEFAULT_ELEVATION_URL),
            ): selector.TextSelector(),
            vol.Required(
                CONF_ELEVATION_THRESHOLD,
                default=get(CONF_ELEVATION_THRESHOLD, DEFAULT_ELEVATION_THRESHOLD),
            ): _number(0, 20, 0.5, "m"),
            vol.Required(
                CONF_TRACK_ALL_ACTIVITIES,
                default=get(CONF_TRACK_ALL_ACTIVITIES, True),
            ): selector.BooleanSelector(),
            vol.Required(
                CONF_REQUIRE_CONFIRMATION,
                default=get(CONF_REQUIRE_CONFIRMATION, False),
            ): selector.BooleanSelector(),
            vol.Required(
                CONF_RETENTION_DAYS,
                default=get(CONF_RETENTION_DAYS, DEFAULT_RETENTION_DAYS),
            ): _number(0, 3650, 1, "d"),
            vol.Required(
                CONF_ROUTING_URL, default=get(CONF_ROUTING_URL, DEFAULT_ROUTING_URL)
            ): selector.TextSelector(),
        }
    )


class BikeTrackerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial setup."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            entity_id = user_input[CONF_SOURCE_ENTITY]
            await self.async_set_unique_id(f"{DOMAIN}_{entity_id}")
            self._abort_if_unique_id_configured()

            state = self.hass.states.get(entity_id)
            if state is None:
                errors["base"] = "entity_not_found"
            elif "latitude" not in state.attributes:
                errors["base"] = "no_gps"
            else:
                return self.async_create_entry(
                    title=f"{DEFAULT_NAME} ({state.name})",
                    data={CONF_SOURCE_ENTITY: entity_id},
                    options={},
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_SOURCE_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["device_tracker", "person"])
                )
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        return BikeTrackerOptionsFlow()


class BikeTrackerOptionsFlow(OptionsFlow):
    """Let the user retune the detection thresholds."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = dict(self.config_entry.data)
        current.update(self.config_entry.options)
        return self.async_show_form(
            step_id="init", data_schema=_options_schema(current)
        )
