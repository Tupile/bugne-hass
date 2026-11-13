"""Config flow for Bugne."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .api import BugneApiClient, BugneAuthError, BugneConnectionError, BugneError
from .const import (
    CONF_CALENDAR_ENTITY,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_WEATHER_ENTITY,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_PASSWORD, default=""): str,
    }
)

STEP_PASSWORD_SCHEMA = vol.Schema({vol.Optional(CONF_PASSWORD, default=""): str})


async def _validate(hass: Any, host: str, password: str) -> dict[str, Any]:
    """Try to reach the device. Returns status on success.

    Raises BugneAuthError / BugneConnectionError on failure.
    """
    session = async_get_clientsession(hass)
    client = BugneApiClient(host, password, session)
    return await client.get_status()


class BugneConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Bugne."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovered_host: str | None = None
        self._discovered_name: str | None = None
        self._dev_id: str | None = None
        self._reauth_entry: ConfigEntry | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manual setup: ask for host and optional password."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST]
            password = user_input.get(CONF_PASSWORD, "")
            try:
                status = await _validate(self.hass, host, password)
            except BugneAuthError:
                errors["base"] = "invalid_auth"
            except BugneConnectionError:
                errors["base"] = "cannot_connect"
            except BugneError:
                errors["base"] = "unknown"
            else:
                dev_id = str(status.get("id", host)).lower()
                await self.async_set_unique_id(dev_id)
                self._abort_if_unique_id_configured(updates={CONF_HOST: host})
                title = status.get("name") or f"Bugne {dev_id.upper()}"
                return self.async_create_entry(
                    title=title,
                    data={CONF_HOST: host, CONF_PASSWORD: password},
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Handle discovery via the _bugne._tcp.local. zeroconf service."""
        host = discovery_info.host
        properties = discovery_info.properties
        dev_id = str(properties.get("id", "")).lower()
        name = properties.get("name") or ""

        if not dev_id:
            return self.async_abort(reason="no_device_id")

        await self.async_set_unique_id(dev_id)
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})

        self._discovered_host = host
        self._discovered_name = name
        self._dev_id = dev_id

        self.context["title_placeholders"] = {
            "name": name or f"Bugne {dev_id.upper()}"
        }
        return await self.async_step_zeroconf_confirm()

    async def async_step_zeroconf_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm discovery and ask for an optional password."""
        errors: dict[str, str] = {}
        assert self._discovered_host is not None
        assert self._dev_id is not None

        if user_input is not None:
            password = user_input.get(CONF_PASSWORD, "")
            try:
                await _validate(self.hass, self._discovered_host, password)
            except BugneAuthError:
                errors["base"] = "invalid_auth"
            except BugneConnectionError:
                errors["base"] = "cannot_connect"
            except BugneError:
                errors["base"] = "unknown"
            else:
                title = self._discovered_name or f"Bugne {self._dev_id.upper()}"
                return self.async_create_entry(
                    title=title,
                    data={CONF_HOST: self._discovered_host, CONF_PASSWORD: password},
                )

        return self.async_show_form(
            step_id="zeroconf_confirm",
            data_schema=STEP_PASSWORD_SCHEMA,
            errors=errors,
            description_placeholders={
                "name": self._discovered_name or f"Bugne {self._dev_id.upper()}"
            },
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Start the reauth flow when the stored password is rejected."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask only for the new password."""
        errors: dict[str, str] = {}
        assert self._reauth_entry is not None

        if user_input is not None:
            password = user_input.get(CONF_PASSWORD, "")
            host = self._reauth_entry.data[CONF_HOST]
            try:
                await _validate(self.hass, host, password)
            except BugneAuthError:
                errors["base"] = "invalid_auth"
            except BugneConnectionError:
                errors["base"] = "cannot_connect"
            except BugneError:
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    self._reauth_entry,
                    data={**self._reauth_entry.data, CONF_PASSWORD: password},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_PASSWORD_SCHEMA,
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return BugneOptionsFlow()


class BugneOptionsFlow(OptionsFlow):
    """Handle Bugne options: polling interval, agenda screen entities."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=self.config_entry.options.get(
                        CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)),
                # Both optional: shown on the device's agenda screen (push.py).
                # suggested_value, not default, so a field can be emptied.
                vol.Optional(
                    CONF_CALENDAR_ENTITY,
                    description={
                        "suggested_value": self.config_entry.options.get(CONF_CALENDAR_ENTITY)
                    },
                ): selector.EntitySelector(selector.EntitySelectorConfig(domain="calendar")),
                vol.Optional(
                    CONF_WEATHER_ENTITY,
                    description={
                        "suggested_value": self.config_entry.options.get(CONF_WEATHER_ENTITY)
                    },
                ): selector.EntitySelector(selector.EntitySelectorConfig(domain="weather")),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
