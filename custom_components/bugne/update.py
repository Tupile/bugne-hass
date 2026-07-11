"""Update platform for Bugne (GitHub OTA firmware)."""
from __future__ import annotations

import time
from typing import Any

from homeassistant.components.update import (
    UpdateDeviceClass,
    UpdateEntity,
    UpdateEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import BugneConfigEntry
from .coordinator import BugneConfigCoordinator
from .entity import BugneEntity

#: The device reboots to apply an update; keep showing "installing" for a
#: while after async_install returns since the device is briefly unreachable.
INSTALL_HOLD_S = 60


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BugneConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Bugne firmware update entity."""
    coordinator = entry.runtime_data.config_coordinator
    async_add_entities([BugneUpdateEntity(coordinator)])


class BugneUpdateEntity(BugneEntity, UpdateEntity):
    """Firmware update entity backed by GitHub OTA."""

    _attr_translation_key = "firmware"
    _attr_device_class = UpdateDeviceClass.FIRMWARE
    _attr_supported_features = UpdateEntityFeature.INSTALL

    def __init__(self, coordinator: BugneConfigCoordinator) -> None:
        super().__init__(coordinator, "firmware")
        self._install_started_at: float | None = None

    @property
    def _ghota(self) -> dict[str, Any]:
        return (self.coordinator.data or {}).get("ghota", {})

    @property
    def installed_version(self) -> str | None:
        return self._ghota.get("current")

    @property
    def latest_version(self) -> str | None:
        return self._ghota.get("latest") or self._ghota.get("current")

    @property
    def release_url(self) -> str | None:
        latest = self._ghota.get("latest")
        if not latest:
            return None
        return f"https://github.com/Tupile/bugne-releases/releases/tag/v{latest}"

    @property
    def in_progress(self) -> bool:
        if self._install_started_at is None:
            return False
        if time.monotonic() - self._install_started_at > INSTALL_HOLD_S:
            self._install_started_at = None
            return False
        return True

    async def async_install(
        self, version: str | None, backup: bool, **kwargs: Any
    ) -> None:
        self._install_started_at = time.monotonic()
        self.async_write_ha_state()
        await self.coordinator.client.ghota_install()
