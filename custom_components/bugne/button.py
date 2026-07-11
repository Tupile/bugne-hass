"""Button platform for Bugne."""
from __future__ import annotations

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import BugneConfigEntry
from .api import BugneRefusedError
from .const import DOMAIN
from .coordinator import BugneConfigCoordinator, BugneStateCoordinator
from .entity import BugneEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BugneConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Bugne buttons."""
    data = entry.runtime_data
    async_add_entities(
        [
            BugneRebootButton(data.state_coordinator),
            BugneCheckUpdateButton(data.config_coordinator),
            BugneRefreshPodcastsButton(data.config_coordinator),
        ]
    )


class BugneRebootButton(BugneEntity, ButtonEntity):
    """Reboot the device."""

    _attr_translation_key = "reboot"
    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: BugneStateCoordinator) -> None:
        super().__init__(coordinator, "reboot")

    async def async_press(self) -> None:
        await self.coordinator.client.reboot()


class BugneCheckUpdateButton(BugneEntity, ButtonEntity):
    """Trigger a live GitHub OTA check (slow, up to 30 s)."""

    _attr_translation_key = "check_update"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: BugneConfigCoordinator) -> None:
        super().__init__(coordinator, "check_update")

    async def async_press(self) -> None:
        await self.coordinator.client.ghota_check()
        await self.coordinator.async_request_refresh()


class BugneRefreshPodcastsButton(BugneEntity, ButtonEntity):
    """Trigger a podcast RSS refresh."""

    _attr_translation_key = "refresh_podcasts"

    def __init__(self, coordinator: BugneConfigCoordinator) -> None:
        super().__init__(coordinator, "refresh_podcasts")

    async def async_press(self) -> None:
        try:
            await self.coordinator.client.podcasts_refresh()
        except BugneRefusedError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="device_refused",
                translation_placeholders={"message": err.message},
            ) from err
