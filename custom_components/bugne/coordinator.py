"""Data update coordinators for the Bugne integration."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import BugneApiClient, BugneAuthError, BugneConnectionError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass
class BugneDeviceIdentity:
    """Shared, mutable device identity used by both coordinators.

    The state coordinator refreshes name/sw_version on every poll (from
    /api/status); the config coordinator and all entities just read it, so
    device_info stays consistent regardless of which coordinator an entity
    is attached to.
    """

    dev_id: str
    host: str
    name: str
    sw_version: str | None = None


class BugneStateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls fast-changing state: playback and status."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: BugneApiClient,
        identity: BugneDeviceIdentity,
        scan_interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} state ({identity.dev_id})",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.entry = entry
        self.client = client
        self.identity = identity

    @property
    def dev_id(self) -> str:
        return self.identity.dev_id

    @property
    def device_name(self) -> str:
        return self.identity.name

    @property
    def device_sw_version(self) -> str | None:
        return self.identity.sw_version

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            status = await self.client.get_status()
            playback = await self.client.get_playback()
        except BugneAuthError as err:
            raise ConfigEntryAuthFailed from err
        except BugneConnectionError as err:
            raise UpdateFailed(str(err)) from err

        self._sync_identity(status)
        return {"status": status, "playback": playback}

    def _sync_identity(self, status: dict[str, Any]) -> None:
        """Update the shared identity and, if changed, the device registry."""
        new_name = status.get("name") or f"Bugne {self.identity.dev_id.upper()}"
        new_version = status.get("version")
        if new_name == self.identity.name and new_version == self.identity.sw_version:
            return
        self.identity.name = new_name
        self.identity.sw_version = new_version

        device_registry = dr.async_get(self.hass)
        device = device_registry.async_get_device(identifiers={(DOMAIN, self.identity.dev_id)})
        if device is not None:
            device_registry.async_update_device(
                device.id, name=new_name, sw_version=new_version
            )


class BugneConfigCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls slow-changing data: the config document and update status."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: BugneApiClient,
        identity: BugneDeviceIdentity,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} config ({identity.dev_id})",
            update_interval=timedelta(seconds=60),
        )
        self.entry = entry
        self.client = client
        self.identity = identity

    @property
    def dev_id(self) -> str:
        return self.identity.dev_id

    @property
    def device_name(self) -> str:
        return self.identity.name

    @property
    def device_sw_version(self) -> str | None:
        return self.identity.sw_version

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            config = await self.client.get_config()
            ghota = await self.client.get_ghota_status()
        except BugneAuthError as err:
            raise ConfigEntryAuthFailed from err
        except BugneConnectionError as err:
            raise UpdateFailed(str(err)) from err
        return {"config": config, "ghota": ghota}
