"""Base entity for Bugne."""
from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


class BugneEntity(CoordinatorEntity[Any]):
    """Common base for all Bugne entities.

    Works with either the state or the config coordinator: both expose
    `.dev_id` and `.client`, and their `.data` dict always has a "status"
    key (the config coordinator refreshes it via the shared device registry
    update, see coordinator.py) so device_info stays consistent everywhere.

    `has_entity_name` is on, so subclasses only set a `translation_key`
    (or `_attr_name`) for the entity-specific part.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator: Any, key: str) -> None:
        super().__init__(coordinator)
        self._dev_id = coordinator.dev_id
        self._attr_unique_id = f"{self._dev_id}_{key}"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._dev_id)},
            name=self.coordinator.device_name,
            manufacturer="Tupile",
            model="Bugne",
            sw_version=self.coordinator.device_sw_version,
            configuration_url=f"http://{self.coordinator.client.host}",
        )
