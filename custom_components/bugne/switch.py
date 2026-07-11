"""Switch platform for Bugne."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
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
    """Set up Bugne switches, including dynamic per-alarm switches."""
    coordinator = entry.runtime_data.config_coordinator
    known_alarm_indices: set[int] = set()

    @callback
    def _add_new_alarms() -> None:
        config = (coordinator.data or {}).get("config", {})
        alarms = config.get("alarms", [])
        new_entities = [
            BugneAlarmSwitch(coordinator, i)
            for i in range(len(alarms))
            if i not in known_alarm_indices
        ]
        if new_entities:
            known_alarm_indices.update(range(len(alarms)))
            async_add_entities(new_entities)

    async_add_entities(
        [
            BugneGameSwitch(coordinator),
            BugneQuietSwitch(coordinator, 0),
            BugneQuietSwitch(coordinator, 1),
        ]
    )
    _add_new_alarms()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_alarms))


class BugneSwitchBase(BugneEntity, SwitchEntity):
    """Base for config-backed switches: read from config, write via mutate_config."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: BugneConfigCoordinator, key: str) -> None:
        super().__init__(coordinator, key)

    @property
    def _config(self) -> dict[str, Any]:
        return (self.coordinator.data or {}).get("config", {})

    async def _write(self, mutator) -> None:
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


class BugneGameSwitch(BugneSwitchBase):
    """Enable or disable the times-tables game on the device home screen."""

    _attr_translation_key = "game"

    def __init__(self, coordinator: BugneConfigCoordinator) -> None:
        super().__init__(coordinator, "game")

    @property
    def is_on(self) -> bool:
        return bool(self._config.get("ui", {}).get("game"))

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(1)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(0)

    async def _set(self, value: int) -> None:
        def mutator(doc: dict[str, Any]) -> None:
            doc.setdefault("ui", {})["game"] = value

        await self._write(mutator)


class BugneQuietSwitch(BugneSwitchBase):
    """Enable or disable one of the two quiet-hours windows."""

    def __init__(self, coordinator: BugneConfigCoordinator, index: int) -> None:
        self._index = index
        super().__init__(coordinator, f"quiet_{index + 1}")
        self._attr_translation_key = "quiet"
        self._attr_translation_placeholders = {"index": str(index + 1)}

    @property
    def is_on(self) -> bool | None:
        quiet = self._config.get("quiet", [])
        if self._index >= len(quiet):
            return None
        return bool(quiet[self._index].get("enabled"))

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(1)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(0)

    async def _set(self, value: int) -> None:
        index = self._index

        def mutator(doc: dict[str, Any]) -> None:
            quiet = doc.get("quiet", [])
            if index >= len(quiet):
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="entity_gone",
                    translation_placeholders={"item": f"Quiet window {index + 1}"},
                )
            quiet[index]["enabled"] = value

        await self._write(mutator)


class BugneAlarmSwitch(BugneSwitchBase):
    """Enable or disable one alarm entry.

    Bugne has a variable-length `alarms` list; entities are added
    dynamically as new indices appear and report unavailable if their
    index disappears (alarm deleted on the device).
    """

    def __init__(self, coordinator: BugneConfigCoordinator, index: int) -> None:
        self._index = index
        super().__init__(coordinator, f"alarm_{index}")
        # `name` is overridden below with the live HH:MM, so no
        # translation_key here: a static translated name would not be
        # able to carry that dynamic time value.

    @property
    def _alarm(self) -> dict[str, Any] | None:
        alarms = self._config.get("alarms", [])
        if self._index >= len(alarms):
            return None
        return alarms[self._index]

    @property
    def available(self) -> bool:
        return super().available and self._alarm is not None

    @property
    def name(self) -> str | None:
        alarm = self._alarm
        if alarm is None:
            return f"Alarm {self._index + 1}"
        hour = alarm.get("hour", 0)
        minute = alarm.get("minute", 0)
        return f"Alarm {self._index + 1} ({hour:02d}:{minute:02d})"

    @property
    def is_on(self) -> bool | None:
        alarm = self._alarm
        if alarm is None:
            return None
        return bool(alarm.get("enabled"))

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(1)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(0)

    async def _set(self, value: int) -> None:
        index = self._index

        def mutator(doc: dict[str, Any]) -> None:
            alarms = doc.get("alarms", [])
            if index >= len(alarms):
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="entity_gone",
                    translation_placeholders={"item": f"Alarm {index + 1}"},
                )
            alarms[index]["enabled"] = value

        await self._write(mutator)
