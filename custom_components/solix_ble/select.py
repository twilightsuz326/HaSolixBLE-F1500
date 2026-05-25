"""Select platform for Solix BLE."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from SolixBLE.states import DisplayTimeout, LightStatus

from .f1500 import F1500

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from . import SolixBLEConfigEntry


LIGHT_OPTIONS = {
    "off": LightStatus.OFF,
    "low": LightStatus.LOW,
    "medium": LightStatus.MEDIUM,
    "high": LightStatus.HIGH,
}

DISPLAY_TIMEOUT_OPTIONS = {
    "20s": DisplayTimeout.S20,
    "30s": DisplayTimeout.S30,
    "60s": DisplayTimeout.S60,
    "5m": DisplayTimeout.S300,
    "30m": DisplayTimeout.S1800,
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: SolixBLEConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the selects."""
    device = config_entry.runtime_data
    selects: list[SolixSelectEntity] = []

    if type(device) is F1500:
        selects.append(
            SolixSelectEntity(
                device=device,
                name="Light",
                attribute="light",
                state_attribute=None,
                setter_name="set_light_mode",
                options=LIGHT_OPTIONS,
            )
        )
        selects.append(
            SolixSelectEntity(
                device=device,
                name="Display Brightness",
                attribute="display_brightness",
                state_attribute=None,
                setter_name="set_display_mode",
                options=LIGHT_OPTIONS,
            )
        )
        selects.append(
            SolixSelectEntity(
                device=device,
                name="Display Timeout",
                attribute="display_timeout",
                state_attribute=None,
                setter_name="set_display_timeout",
                options=DISPLAY_TIMEOUT_OPTIONS,
            )
        )

    async_add_entities(selects)


class SolixSelectEntity(SelectEntity, RestoreEntity):
    """Representation of a Solix BLE select."""

    _attr_has_entity_name = True

    def __init__(
        self,
        device,
        name: str,
        attribute: str,
        state_attribute: str | None,
        setter_name: str,
        options: dict[str, Any],
    ) -> None:
        self._device = device
        self._state_attribute = state_attribute
        self._setter = getattr(device, setter_name)
        self._options_map = options
        self._reverse_options_map = {value: key for key, value in options.items()}
        self._optimistic_option: str | None = None

        self._attr_name = name
        self._attr_unique_id = f"{device.address}_{attribute}"
        self._attr_options = list(options.keys())
        self._attr_device_info = DeviceInfo(
            name=device.name,
            connections={(CONNECTION_BLUETOOTH, device.address)},
        )
        self._update_updatable_attributes()

    async def async_added_to_hass(self) -> None:
        self._device.add_callback(self._state_change_callback)
        if self._state_attribute is None:
            last_state = await self.async_get_last_state()
            if last_state is not None and last_state.state in self._options_map:
                self._optimistic_option = last_state.state
                self._attr_current_option = last_state.state

    async def async_will_remove_from_hass(self) -> None:
        self._device.remove_callback(self._state_change_callback)

    def _update_updatable_attributes(self) -> None:
        self._attr_available = self._device.available or self._device.connected

        if self._state_attribute is None:
            self._attr_current_option = self._optimistic_option
            return

        state = getattr(self._device, self._state_attribute)
        self._attr_current_option = self._reverse_options_map.get(state)
        _LOGGER.debug(
            "Select update for %s: available=%s raw_state=%r option=%r",
            self._attr_name,
            self._attr_available,
            state,
            self._attr_current_option,
        )

    def _state_change_callback(self) -> None:
        self._update_updatable_attributes()
        self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        await self._setter(self._options_map[option])
        if self._state_attribute is None:
            self._optimistic_option = option
            self._attr_current_option = option
            self.async_write_ha_state()
