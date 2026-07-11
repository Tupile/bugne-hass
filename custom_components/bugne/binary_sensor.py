"""Binary sensor platform for Bugne."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import BugneConfigEntry
from .coordinator import BugneStateCoordinator
from .entity import BugneEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BugneConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Bugne binary sensor."""
    coordinator = entry.runtime_data.state_coordinator
    async_add_entities([BugneSdPresentBinarySensor(coordinator)])


class BugneSdPresentBinarySensor(BugneEntity, BinarySensorEntity):
    """Whether an SD card is currently inserted."""

    _attr_translation_key = "sd_present"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: BugneStateCoordinator) -> None:
        super().__init__(coordinator, "sd_present")

    @property
    def is_on(self) -> bool | None:
        status = (self.coordinator.data or {}).get("status", {})
        sd = status.get("sd") or {}
        return sd.get("present")
