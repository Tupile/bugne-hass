"""Media player platform for Bugne."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import voluptuous as vol
from homeassistant.components import webhook
from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_platform
from homeassistant.helpers.network import NoURLAvailableError, get_url
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import BugneConfigEntry
from .api import BugneRefusedError
from .const import (
    ATTR_ACTIONS,
    ATTR_ID,
    ATTR_LABEL,
    ATTR_MESSAGE,
    ATTR_SLEEP_MIN,
    ATTR_TITLE,
    ATTR_VALUE,
    CONF_WEBHOOK_ID,
    DOMAIN,
    SERVICE_CLEAR_NOTIFICATION,
    SERVICE_SEND_NOTIFICATION,
    SERVICE_SET_SLEEP_TIMER,
)
from .notify import MAX_ACTIONS, build_payload
from .entity import BugneEntity

_LOGGER = logging.getLogger(__name__)

SOURCE_RADIO = "radio"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BugneConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Bugne media player."""
    data = entry.runtime_data
    async_add_entities([BugneMediaPlayer(data.state_coordinator, data.config_coordinator)])

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_SET_SLEEP_TIMER,
        {vol.Required(ATTR_VALUE): vol.All(vol.Coerce(int), vol.Range(min=-1))},
        "async_set_sleep_timer",
    )
    platform.async_register_entity_service(
        SERVICE_SEND_NOTIFICATION,
        {
            vol.Required(ATTR_MESSAGE): cv.string,
            vol.Optional(ATTR_TITLE): cv.string,
            vol.Optional(ATTR_ID): cv.string,
            vol.Optional(ATTR_ACTIONS): vol.All(
                cv.ensure_list,
                vol.Length(max=MAX_ACTIONS),
                [{vol.Required(ATTR_ID): cv.string, vol.Required(ATTR_LABEL): cv.string}],
            ),
        },
        "async_send_notification",
    )
    platform.async_register_entity_service(
        SERVICE_CLEAR_NOTIFICATION, None, "async_clear_notification"
    )


class BugneMediaPlayer(BugneEntity, MediaPlayerEntity):
    """Represents the Bugne player.

    The device has no "off" state (it is always on, just idle), so the
    state never becomes MediaPlayerState.OFF.
    """

    _attr_translation_key = "player"
    _BASE_FEATURES = (
        MediaPlayerEntityFeature.PLAY
        | MediaPlayerEntityFeature.PAUSE
        | MediaPlayerEntityFeature.STOP
        | MediaPlayerEntityFeature.NEXT_TRACK
        | MediaPlayerEntityFeature.PREVIOUS_TRACK
        | MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.SELECT_SOURCE
        | MediaPlayerEntityFeature.PLAY_MEDIA
    )

    @property
    def supported_features(self) -> MediaPlayerEntityFeature:
        # SEEK follows the device's "seekable" flag (firmware >= 1.5.0, true
        # while a local FLAC/MP3/M4A file plays; absent on older firmware).
        features = self._BASE_FEATURES
        if self._playback.get("seekable"):
            features |= MediaPlayerEntityFeature.SEEK
        return features

    def __init__(self, state_coordinator, config_coordinator) -> None:
        super().__init__(state_coordinator, "player")
        self._config_coordinator = config_coordinator
        self._remove_config_listener = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._remove_config_listener = self._config_coordinator.async_add_listener(
            self._handle_config_update
        )

    async def async_will_remove_from_hass(self) -> None:
        if self._remove_config_listener is not None:
            self._remove_config_listener()
        await super().async_will_remove_from_hass()

    def _handle_config_update(self) -> None:
        self.async_write_ha_state()

    def _handle_coordinator_update(self) -> None:
        if self.coordinator.data:
            self._attr_media_position_updated_at = datetime.now(timezone.utc)
        super()._handle_coordinator_update()

    @property
    def _playback(self) -> dict[str, Any]:
        return (self.coordinator.data or {}).get("playback", {})

    @property
    def _config(self) -> dict[str, Any]:
        return (self._config_coordinator.data or {}).get("config", {})

    @property
    def _webradios(self) -> list[dict[str, Any]]:
        return self._config.get("webradios", [])

    @property
    def state(self) -> MediaPlayerState:
        # `available` (below) covers the unavailable case; this device has
        # no "off" state, it is either idle, paused or playing.
        playback = self._playback
        if not playback.get("active"):
            return MediaPlayerState.IDLE
        if playback.get("paused"):
            return MediaPlayerState.PAUSED
        return MediaPlayerState.PLAYING

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    @property
    def volume_level(self) -> float | None:
        volume = self._playback.get("volume")
        if volume is None:
            return None
        return volume / 100

    @property
    def source_list(self) -> list[str]:
        return [radio["name"] for radio in self._webradios]

    @property
    def source(self) -> str | None:
        if self._playback.get("source") != SOURCE_RADIO:
            return None
        title = self._playback.get("title", "")
        for radio in self._webradios:
            if radio.get("name") == title:
                return radio["name"]
        return None

    @property
    def media_title(self) -> str | None:
        return self._playback.get("title") or None

    @property
    def media_artist(self) -> str | None:
        return self._playback.get("artist") or None

    @property
    def app_name(self) -> str | None:
        return self._playback.get("source")

    @property
    def media_duration(self) -> int | None:
        dur_ms = self._playback.get("dur_ms") or 0
        return dur_ms // 1000 or None

    @property
    def media_position(self) -> int | None:
        return self._playback.get("pos_ms", 0) // 1000

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {ATTR_SLEEP_MIN: self._playback.get("sleep_min")}

    async def _optimistic_refresh(self) -> None:
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def _send(self, action: str, value: Any = None, title: str | None = None) -> None:
        try:
            await self.coordinator.client.playback_action(action, value=value, title=title)
        except BugneRefusedError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="device_refused",
                translation_placeholders={"message": err.message},
            ) from err

    async def async_media_play(self) -> None:
        playback = self._playback
        if playback.get("active") and playback.get("paused"):
            await self._send("toggle")
            await self._optimistic_refresh()

    async def async_media_pause(self) -> None:
        playback = self._playback
        if playback.get("active") and not playback.get("paused"):
            await self._send("toggle")
            await self._optimistic_refresh()

    async def async_media_play_pause(self) -> None:
        await self._send("toggle")
        await self._optimistic_refresh()

    async def async_media_stop(self) -> None:
        await self._send("stop")
        await self._optimistic_refresh()

    async def async_media_next_track(self) -> None:
        await self._send("next")
        await self._optimistic_refresh()

    async def async_media_previous_track(self) -> None:
        await self._send("prev")
        await self._optimistic_refresh()

    async def async_set_volume_level(self, volume: float) -> None:
        await self._send("volume", value=round(volume * 100))
        await self._optimistic_refresh()

    async def async_media_seek(self, position: float) -> None:
        await self._send("seek", value=round(position * 1000))
        await self._optimistic_refresh()

    async def async_select_source(self, source: str) -> None:
        for radio in self._webradios:
            if radio.get("name") == source:
                await self._send("radio", value=radio["id"])
                await self._optimistic_refresh()
                return
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="unknown_source",
            translation_placeholders={"source": source},
        )

    async def async_play_media(self, media_type: str, media_id: str, **kwargs: Any) -> None:
        title = kwargs.get("metadata", {}).get("title") if kwargs.get("metadata") else None
        await self._send("path", value=media_id, title=title)
        await self._optimistic_refresh()

    async def _post_notification(self, payload: dict[str, Any]) -> None:
        status = (self.coordinator.data or {}).get("status") or {}
        if "notify" not in status:
            # An older firmware answers the unknown route with a redirect.
            raise HomeAssistantError(
                "This Bugne firmware has no notifications: update the device"
            )
        try:
            await self.coordinator.client.post_notification(payload)
        except BugneRefusedError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="device_refused",
                translation_placeholders={"message": err.message},
            ) from err

    async def async_send_notification(
        self,
        message: str,
        title: str | None = None,
        id: str | None = None,  # noqa: A002 (the service field name)
        actions: list[dict[str, str]] | None = None,
    ) -> None:
        """Entity service: show a notification, with up to two answers.

        The device posts the chosen answer to this entry's webhook, which
        fires the bugne_notification_action event.
        """
        reply_url = None
        if actions:
            # The webhook is local only: an external URL (reverse proxy) would
            # be answered 200 and dropped, a silently dead button.
            try:
                base = get_url(self.hass, allow_external=False, allow_cloud=False)
            except NoURLAvailableError as err:
                raise HomeAssistantError(
                    "Home Assistant has no URL the device can answer to: "
                    "set the local network URL in Settings, System, Network"
                ) from err
            webhook_id = self.coordinator.entry.data[CONF_WEBHOOK_ID]
            reply_url = f"{base}{webhook.async_generate_path(webhook_id)}"
        try:
            payload = build_payload(message, title, id, actions, reply_url)
        except ValueError as err:
            raise HomeAssistantError(f"Invalid notification: {err}") from err
        await self._post_notification(payload)

    async def async_clear_notification(self) -> None:
        """Entity service: remove the notification shown on the device."""
        await self._post_notification({})

    async def async_set_sleep_timer(self, value: int) -> None:
        """Entity service: set or clear the sleep timer (minutes, -1 or 0)."""
        await self._send("sleep", value=value)
        await self._optimistic_refresh()
