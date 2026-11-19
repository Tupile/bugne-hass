"""The Bugne integration."""
from __future__ import annotations

import logging
from dataclasses import dataclass

import aiohttp
from aiohttp import web
from homeassistant.components import webhook
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import BugneApiClient, BugneAuthError, BugneConnectionError
from .const import (
    CONF_CALENDAR_ENTITY,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_WEATHER_ENTITY,
    CONF_WEBHOOK_ID,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    EVENT_NOTIFICATION_ACTION,
    PLATFORMS,
)
from .coordinator import BugneConfigCoordinator, BugneDeviceIdentity, BugneStateCoordinator
from .notify import parse_reply
from .push import AgendaPusher

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

    _async_register_webhook(hass, entry, dev_id)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Agenda screen: only when the user picked a calendar or a weather entity.
    calendar_entity = entry.options.get(CONF_CALENDAR_ENTITY)
    weather_entity = entry.options.get(CONF_WEATHER_ENTITY)
    if calendar_entity or weather_entity:
        pusher = AgendaPusher(hass, client, state_coordinator, calendar_entity, weather_entity)
        pusher.async_start()
        entry.async_on_unload(pusher.async_stop)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


def _async_register_webhook(hass: HomeAssistant, entry: BugneConfigEntry, dev_id: str) -> None:
    """Register the webhook the device posts notification answers to.

    One webhook per device. Its id is generated once and kept in the entry
    data, so a notification sent before a restart can still be answered. This
    runs before the update listener is added, so storing the id does not
    reload the entry.
    """
    webhook_id = entry.data.get(CONF_WEBHOOK_ID)
    if not webhook_id:
        webhook_id = webhook.async_generate_id()
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_WEBHOOK_ID: webhook_id}
        )

    async def handle(
        hass: HomeAssistant, webhook_id: str, request: web.Request
    ) -> web.Response | None:
        try:
            reply = parse_reply(await request.json())
        except ValueError:
            reply = None
        if reply is None:
            return web.Response(status=400)
        device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, dev_id)})
        hass.bus.async_fire(
            EVENT_NOTIFICATION_ACTION,
            {
                "device_id": device.id if device else None,
                "entry_id": entry.entry_id,
                "id": reply[0],
                "action": reply[1],
            },
        )
        return None

    webhook.async_register(
        hass,
        DOMAIN,
        f"Bugne {dev_id.upper()} notification answer",
        webhook_id,
        handle,
        local_only=True,
        allowed_methods=["POST"],
    )
    entry.async_on_unload(lambda: webhook.async_unregister(hass, webhook_id))


async def _async_update_listener(hass: HomeAssistant, entry: BugneConfigEntry) -> None:
    """Reload the entry when its options change (scan interval, agenda entities)."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: BugneConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
