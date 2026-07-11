"""The Bugne integration."""
from __future__ import annotations

import logging
from dataclasses import dataclass

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import BugneApiClient, BugneAuthError, BugneConnectionError
from .const import CONF_HOST, CONF_PASSWORD, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, PLATFORMS
from .coordinator import BugneConfigCoordinator, BugneDeviceIdentity, BugneStateCoordinator

_LOGGER = logging.getLogger(__name__)

type BugneConfigEntry = ConfigEntry[BugneData]


@dataclass
class BugneData:
    """Runtime data stored on the config entry."""

    client: BugneApiClient
    state_coordinator: BugneStateCoordinator
    config_coordinator: BugneConfigCoordinator
    dev_id: str


async def async_setup_entry(hass: HomeAssistant, entry: BugneConfigEntry) -> bool:
    """Set up Bugne from a config entry."""
    host = entry.data[CONF_HOST]
    password = entry.data.get(CONF_PASSWORD, "")
    dev_id = entry.unique_id or entry.entry_id

    session = async_get_clientsession(hass)
    client = BugneApiClient(host, password, session)

    try:
        status = await client.get_status()
    except BugneAuthError as err:
        raise ConfigEntryAuthFailed from err
    except BugneConnectionError as err:
        raise ConfigEntryNotReady(f"cannot connect to Bugne at {host}") from err

    identity = BugneDeviceIdentity(
        dev_id=dev_id,
        host=host,
        name=status.get("name") or f"Bugne {dev_id.upper()}",
        sw_version=status.get("version"),
    )

    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    state_coordinator = BugneStateCoordinator(hass, entry, client, identity, scan_interval)
    config_coordinator = BugneConfigCoordinator(hass, entry, client, identity)

    await state_coordinator.async_config_entry_first_refresh()
    await config_coordinator.async_config_entry_first_refresh()

    entry.runtime_data = BugneData(
        client=client,
        state_coordinator=state_coordinator,
        config_coordinator=config_coordinator,
        dev_id=dev_id,
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: BugneConfigEntry) -> None:
    """Reload the entry when its options change (e.g. scan_interval)."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: BugneConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
