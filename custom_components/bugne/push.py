"""Push the agenda + weather data to a Bugne device.

The user picks a calendar and a weather entity in the integration options.
This module reads them, lets agenda.py build the text, and POSTs it to the
device, which only displays it. The device keeps the data in RAM and hides
it after two hours without a push, so the payload is sent:
- when its content changed (entity state change, or the 15 minute refresh
  that also moves "Today" to "Tomorrow" and updates the forecasts),
- every 30 minutes even when unchanged,
- when the device reports it holds no data (after a reboot).
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import timedelta
from typing import Any

import voluptuous as vol
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util

from .agenda import MAX_EVENTS, build_payload
from .api import BugneApiClient, BugneError
from .coordinator import BugneStateCoordinator

_LOGGER = logging.getLogger(__name__)

REFRESH_INTERVAL = timedelta(minutes=15)
RESEND_AFTER_S = 30 * 60
REPUSH_MIN_GAP_S = 60
CALENDAR_DAYS = 7

# WeatherEntityFeature values, kept local so this module does not depend on
# the weather component being loaded.
_FORECAST_DAILY = 1
_FORECAST_HOURLY = 2


class AgendaPusher:
    """Keep one device's agenda screen up to date."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: BugneApiClient,
        coordinator: BugneStateCoordinator,
        calendar_entity: str | None,
        weather_entity: str | None,
    ) -> None:
        self._hass = hass
        self._client = client
        self._coordinator = coordinator
        self._calendar = calendar_entity
        self._weather = weather_entity
        self._unsubs: list[Any] = []
        self._task: asyncio.Task[None] | None = None
        self._dirty = False
        self._force = False
        self._last_sent: dict[str, Any] | None = None
        self._last_sent_at = 0.0
        self._last_attempt_at = 0.0
        self._warned_unsupported = False
        self._last_events: list[dict[str, Any]] | None = None

    @callback
    def async_start(self) -> None:
        entities = [e for e in (self._calendar, self._weather) if e]
        self._unsubs.append(
            async_track_state_change_event(self._hass, entities, self._on_state)
        )
        self._unsubs.append(
            async_track_time_interval(self._hass, self._on_timer, REFRESH_INTERVAL)
        )
        self._unsubs.append(self._coordinator.async_add_listener(self._on_status))
        self._schedule()

    @callback
    def async_stop(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        if self._task is not None:
            self._task.cancel()
            self._task = None

    @callback
    def _on_state(self, event: Event) -> None:
        self._schedule()

    @callback
    def _on_timer(self, now: Any) -> None:
        self._schedule()

    @callback
    def _on_status(self) -> None:
        """Push again when the device says it holds no fresh data."""
        if not self._coordinator.last_update_success:
            return
        status = (self._coordinator.data or {}).get("status") or {}
        if status.get("agenda") is not False:
            return
        if not self._last_sent:
            return  # nothing worth showing was built yet
        if time.monotonic() - self._last_attempt_at < REPUSH_MIN_GAP_S:
            return
        self._schedule(force=True)

    @callback
    def _schedule(self, force: bool = False) -> None:
        self._force = self._force or force
        if self._task is not None and not self._task.done():
            self._dirty = True
            return
        self._task = self._hass.async_create_background_task(
            self._run(), name="bugne agenda push"
        )

    async def _run(self) -> None:
        while True:
            self._dirty = False
            try:
                await self._refresh()
            except Exception:  # noqa: BLE001 - a push must never break the entry
                _LOGGER.exception("Bugne agenda push failed")
            if not self._dirty:
                return

    def _supported(self) -> bool:
        status = (self._coordinator.data or {}).get("status") or {}
        if "agenda" in status:
            return True
        if not self._warned_unsupported:
            self._warned_unsupported = True
            _LOGGER.warning(
                "%s: this firmware has no agenda screen, update the device "
                "to use the calendar and weather options",
                self._coordinator.device_name,
            )
        return False

    async def _refresh(self) -> None:
        if not self._supported():
            return
        force, self._force = self._force, False
        payload = await self._build()
        now = time.monotonic()
        unchanged = payload == self._last_sent
        if unchanged and not force and now - self._last_sent_at < RESEND_AFTER_S:
            return
        if not payload and not self._last_sent:
            return  # nothing to show and nothing to clear
        self._last_attempt_at = now
        try:
            await self._client.post_agenda(payload)
        except BugneError as err:
            # Device offline or busy: the next refresh or status poll retries.
            _LOGGER.debug("agenda push to %s failed: %s", self._client.host, err)
            return
        self._last_sent = payload
        self._last_sent_at = now

    async def _build(self) -> dict[str, Any]:
        now = dt_util.now()
        events = await self._events(now) if self._calendar else None
        condition = temperature = unit = None
        daily = hourly = None
        if self._weather:
            state = self._hass.states.get(self._weather)
            if state is not None:
                condition = state.state
                temperature = state.attributes.get("temperature")
                unit = (
                    state.attributes.get("temperature_unit")
                    or self._hass.config.units.temperature_unit
                )
                features = state.attributes.get("supported_features") or 0
                if features & _FORECAST_DAILY:
                    daily = await self._forecast("daily")
                if features & _FORECAST_HOURLY:
                    hourly = await self._forecast("hourly")
        return build_payload(
            events=events,
            condition=condition,
            temperature=temperature,
            unit=unit,
            daily=daily,
            hourly=hourly,
            language=self._hass.config.language,
            now=now,
        )

    async def _events(self, now: Any) -> list[dict[str, Any]] | None:
        """Upcoming events of the calendar.

        When the call fails (calendar not loaded yet, provider outage) the
        last good list is reused, so the device does not show "nothing
        planned" over valid data. None before any successful call.
        """
        try:
            response = await self._hass.services.async_call(
                "calendar",
                "get_events",
                {
                    "entity_id": self._calendar,
                    "start_date_time": now.isoformat(),
                    "end_date_time": (now + timedelta(days=CALENDAR_DAYS)).isoformat(),
                },
                blocking=True,
                return_response=True,
            )
        except (HomeAssistantError, ValueError, vol.Invalid) as err:
            _LOGGER.debug("calendar.get_events failed for %s: %s", self._calendar, err)
            return self._last_events
        events = ((response or {}).get(self._calendar) or {}).get("events") or []
        # agenda.py sorts and keeps MAX_EVENTS; cap what is handed over anyway.
        self._last_events = list(events)[: MAX_EVENTS * 10]
        return self._last_events

    async def _forecast(self, kind: str) -> list[dict[str, Any]] | None:
        try:
            response = await self._hass.services.async_call(
                "weather",
                "get_forecasts",
                {"entity_id": self._weather, "type": kind},
                blocking=True,
                return_response=True,
            )
        except (HomeAssistantError, ValueError, vol.Invalid) as err:
            _LOGGER.debug("weather.get_forecasts (%s) failed: %s", kind, err)
            return None
        return ((response or {}).get(self._weather) or {}).get("forecast")
