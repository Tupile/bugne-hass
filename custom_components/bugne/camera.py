"""Camera platform for Bugne: an on-demand screenshot of the device screen."""
from __future__ import annotations

import io
import time
from typing import Any

from homeassistant.components.camera import Camera
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import BugneConfigEntry
from .coordinator import BugneStateCoordinator
from .entity import BugneEntity

CACHE_S = 5


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BugneConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Bugne screenshot camera."""
    data = entry.runtime_data
    async_add_entities([BugneScreenshotCamera(data.state_coordinator)])


class BugneScreenshotCamera(BugneEntity, Camera):
    """Shows the live device screen, fetched on demand (not a video stream)."""

    _attr_translation_key = "screen"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_content_type = "image/png"
    _attr_is_streaming = False

    def __init__(self, coordinator: BugneStateCoordinator) -> None:
        BugneEntity.__init__(self, coordinator, "screen")
        Camera.__init__(self)
        self._cached_frame: bytes | None = None
        self._cached_at: float = 0.0

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        now = time.monotonic()
        if self._cached_frame is not None and now - self._cached_at < CACHE_S:
            return self._cached_frame

        bmp_bytes = await self.coordinator.client.get_screenshot()
        png_bytes = await self.hass.async_add_executor_job(_bmp_to_png, bmp_bytes)
        self._cached_frame = png_bytes
        self._cached_at = now
        return png_bytes


def _bmp_to_png(bmp_bytes: bytes) -> bytes:
    """Convert the device's 16bpp RGB565 BI_BITFIELDS BMP to PNG.

    Pillow decodes this BMP variant directly. If a future firmware/Pillow
    combination rejects the BI_BITFIELDS header, fall back to a manual
    RGB565 -> RGB888 decode of the pixel array instead of this helper.
    """
    from PIL import Image

    with Image.open(io.BytesIO(bmp_bytes)) as image:
        rgb = image.convert("RGB")
        out = io.BytesIO()
        rgb.save(out, format="PNG")
        return out.getvalue()
