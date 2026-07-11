"""Sensor platform for Bugne."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import (
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfInformation,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import BugneConfigEntry
from .coordinator import BugneStateCoordinator
from .entity import BugneEntity

UPTIME_QUANTIZE_S = 30


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BugneConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Bugne sensors."""
    coordinator = entry.runtime_data.state_coordinator
    async_add_entities(
        [
            BugneRssiSensor(coordinator),
            BugneUptimeSensor(coordinator),
            BugneHeapFreeSensor(coordinator),
            BugneSdFreeSensor(coordinator),
        ]
    )


class BugneSensorBase(BugneEntity, SensorEntity):
    """Base for the diagnostic sensors, all backed by the state coordinator."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: BugneStateCoordinator, key: str) -> None:
        super().__init__(coordinator, key)

    @property
    def _status(self) -> dict[str, Any]:
        return (self.coordinator.data or {}).get("status", {})


class BugneRssiSensor(BugneSensorBase):
    """Wi-Fi signal strength."""

    _attr_translation_key = "rssi"
    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: BugneStateCoordinator) -> None:
        super().__init__(coordinator, "rssi")

    @property
    def native_value(self) -> int | None:
        return self._status.get("rssi")


class BugneUptimeSensor(BugneSensorBase):
    """Device uptime, exposed as a timestamp (last boot time).

    Quantized to 30 s so the state does not churn every poll.
    """

    _attr_translation_key = "uptime"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: BugneStateCoordinator) -> None:
        super().__init__(coordinator, "uptime")

    @property
    def native_value(self) -> datetime | None:
        uptime_s = self._status.get("uptime_s")
        if uptime_s is None:
            return None
        quantized = (uptime_s // UPTIME_QUANTIZE_S) * UPTIME_QUANTIZE_S
        return datetime.now(timezone.utc) - timedelta(seconds=quantized)


class BugneHeapFreeSensor(BugneSensorBase):
    """Free heap memory, disabled by default (noisy, developer-facing)."""

    _attr_translation_key = "heap_free"
    _attr_device_class = SensorDeviceClass.DATA_SIZE
    _attr_native_unit_of_measurement = UnitOfInformation.BYTES
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: BugneStateCoordinator) -> None:
        super().__init__(coordinator, "heap_free")

    @property
    def native_value(self) -> int | None:
        return self._status.get("heap_free")


class BugneSdFreeSensor(BugneSensorBase):
    """Free SD card space, None when no card is present."""

    _attr_translation_key = "sd_free"
    _attr_device_class = SensorDeviceClass.DATA_SIZE
    _attr_native_unit_of_measurement = UnitOfInformation.BYTES
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: BugneStateCoordinator) -> None:
        super().__init__(coordinator, "sd_free")

    @property
    def native_value(self) -> int | None:
        sd = self._status.get("sd") or {}
        if not sd.get("present"):
            return None
        return sd.get("free")
