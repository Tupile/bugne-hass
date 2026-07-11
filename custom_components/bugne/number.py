"""Number platform for Bugne."""
from __future__ import annotations

from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import BugneConfigEntry
from .api import BugneError
from .const import DOMAIN
from .coordinator import BugneConfigCoordinator
from .entity import BugneEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BugneConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Bugne volume ceiling number entity."""
    coordinator = entry.runtime_data.config_coordinator
    async_add_entities([BugneVolumeMaxNumber(coordinator)])


class BugneVolumeMaxNumber(BugneEntity, NumberEntity):
    """Parental volume ceiling (ui.volume_max)."""

    _attr_translation_key = "volume_max"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min_value = 10
    _attr_native_max_value = 100
    _attr_native_step = 5
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: BugneConfigCoordinator) -> None:
        super().__init__(coordinator, "volume_max")

    @property
    def native_value(self) -> int | None:
        config = (self.coordinator.data or {}).get("config", {})
        return config.get("ui", {}).get("volume_max")

    async def async_set_native_value(self, value: float) -> None:
        new_value = int(value)

        def mutator(doc: dict[str, Any]) -> None:
            doc.setdefault("ui", {})["volume_max"] = new_value

        try:
            await self.coordinator.client.mutate_config(mutator)
        except BugneError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="config_write_failed",
                translation_placeholders={"message": str(err)},
            ) from err
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()
