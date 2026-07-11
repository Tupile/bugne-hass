"""Diagnostics support for Bugne."""
from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.redact import async_redact_data

from . import BugneConfigEntry

TO_REDACT_WEBRADIO = {"url"}
TO_REDACT_PODCAST = {"rss_url"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: BugneConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    data = entry.runtime_data
    status = (data.state_coordinator.data or {}).get("status", {})
    playback = (data.state_coordinator.data or {}).get("playback", {})
    config = dict((data.config_coordinator.data or {}).get("config", {}))

    config["webradios"] = [
        async_redact_data(radio, TO_REDACT_WEBRADIO)
        for radio in config.get("webradios", [])
    ]
    config["podcasts"] = [
        async_redact_data(podcast, TO_REDACT_PODCAST)
        for podcast in config.get("podcasts", [])
    ]

    return {
        "status": status,
        "playback": playback,
        "config": config,
    }
