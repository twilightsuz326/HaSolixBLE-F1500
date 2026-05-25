"""Minimal sensor platform for Solix BLE."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from SolixBLE.const import (
    DEFAULT_METADATA_FLOAT,
    DEFAULT_METADATA_INT,
    DEFAULT_METADATA_STRING,
)
from homeassistant.components.sensor import SensorEntity
from homeassistant.components.sensor.const import SensorDeviceClass
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .f1500 import F1500

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from . import SolixBLEConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: SolixBLEConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Solix BLE sensors."""
    device = config_entry.runtime_data
    sensors: list[SolixSensorEntity] = []

    _LOGGER.debug(
        "Setting up sensors for %s using device class %s",
        getattr(device, "name", "unknown"),
        type(device).__name__,
    )

    def add_sensor(name: str, unit: str | None, attribute: str, device_class=None) -> None:
        if not hasattr(device, attribute):
            return
        sensors.append(SolixSensorEntity(device, name, unit, attribute, device_class))

    if type(device) is F1500:
        add_sensor("Hours Remaining", "h", "hours_remaining")
        add_sensor("Days Remaining", "d", "days_remaining")
        add_sensor("Time Remaining", "h", "time_remaining")
        add_sensor("Battery Percentage", "%", "battery_percentage", SensorDeviceClass.BATTERY)
        add_sensor("Charging Status", None, "charging_status")
        add_sensor("Temperature", UnitOfTemperature.CELSIUS, "temperature", SensorDeviceClass.TEMPERATURE)
        add_sensor("Total Power In", "W", "power_in", SensorDeviceClass.POWER)
        add_sensor("Total Power Out", "W", "power_out", SensorDeviceClass.POWER)
        add_sensor("AC Power In", "W", "ac_power_in", SensorDeviceClass.POWER)
        add_sensor("AC Power Out", "W", "ac_power_out", SensorDeviceClass.POWER)
        add_sensor("Solar Power In", "W", "solar_power_in", SensorDeviceClass.POWER)
        add_sensor("DC Power Out", "W", "dc_power_out", SensorDeviceClass.POWER)
        add_sensor("USB C1 Power", "W", "usb_c1_power", SensorDeviceClass.POWER)
        add_sensor("USB C2 Power", "W", "usb_c2_power", SensorDeviceClass.POWER)
        add_sensor("USB A1 Power", "W", "usb_a1_power", SensorDeviceClass.POWER)
        add_sensor("USB A2 Power", "W", "usb_a2_power", SensorDeviceClass.POWER)
        add_sensor("USB A3 Power", "W", "usb_a3_power", SensorDeviceClass.POWER)
        add_sensor("USB A4 Power", "W", "usb_a4_power", SensorDeviceClass.POWER)
        add_sensor("Firmware Version", None, "software_version")
        add_sensor("Controller Firmware Version", None, "software_version_controller")
        add_sensor("Serial Number", None, "serial_number")
    else:
        add_sensor("Battery Percentage", "%", "battery_percentage", SensorDeviceClass.BATTERY)
        add_sensor("Temperature", UnitOfTemperature.CELSIUS, "temperature", SensorDeviceClass.TEMPERATURE)
        add_sensor("Total Power In", "W", "power_in", SensorDeviceClass.POWER)
        add_sensor("Total Power Out", "W", "power_out", SensorDeviceClass.POWER)
        add_sensor("Firmware Version", None, "software_version")

    _LOGGER.debug("Adding %d sensor entities for device class %s", len(sensors), type(device).__name__)
    async_add_entities(sensors)


class SolixSensorEntity(SensorEntity):
    """Representation of a Solix BLE sensor."""

    _attr_has_entity_name = True

    def __init__(self, device: Any, name: str, unit: str | None, attribute_name: str, device_class=None) -> None:
        self._device = device
        self._attribute_name = attribute_name
        self._attr_name = name
        self._attr_unique_id = f"{device.address}_{attribute_name}"
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_device_info = DeviceInfo(
            name=device.name,
            connections={(CONNECTION_BLUETOOTH, device.address)},
        )
        self._attr_available = device.available
        self._update_value()

    async def async_added_to_hass(self) -> None:
        self._device.add_callback(self._state_change_callback)

    async def async_will_remove_from_hass(self) -> None:
        self._device.remove_callback(self._state_change_callback)

    def _update_value(self) -> None:
        # Keep entities usable through brief BLE drops and reconnect churn.
        # Once we have seen telemetry, prefer the last known value over
        # flipping the entity to unavailable immediately.
        has_cached_data = getattr(self._device, "_data", None) is not None
        self._attr_available = self._device.available or has_cached_data or self._device.connected
        value = getattr(self._device, self._attribute_name, None)
        _LOGGER.debug(
            "Sensor update for %s (%s): available=%s device_available=%s connected=%s cached_data=%s raw_value=%r",
            self._attr_name,
            self._attribute_name,
            self._attr_available,
            self._device.available,
            self._device.connected,
            has_cached_data,
            value,
        )
        if value in (None, DEFAULT_METADATA_INT, DEFAULT_METADATA_FLOAT, DEFAULT_METADATA_STRING):
            _LOGGER.debug(
                "Sensor %s (%s) keeping previous value because current value is metadata default",
                self._attr_name,
                self._attribute_name,
            )
            return
        self._attr_native_value = value
        _LOGGER.debug(
            "Sensor %s (%s) wrote native value %r",
            self._attr_name,
            self._attribute_name,
            self._attr_native_value,
        )

    def _state_change_callback(self) -> None:
        _LOGGER.debug(
            "State change callback for %s (%s)",
            self._attr_name,
            self._attribute_name,
        )
        self._update_value()
        self.async_write_ha_state()
