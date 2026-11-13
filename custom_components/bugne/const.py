"""Constants for the Bugne integration."""
from __future__ import annotations

from homeassistant.const import Platform

from .api import SUPPORTED_SCHEMA_VERSION as SUPPORTED_SCHEMA_VERSION

DOMAIN = "bugne"

PLATFORMS: list[Platform] = [
    Platform.MEDIA_PLAYER,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.NUMBER,
    Platform.BUTTON,
    Platform.UPDATE,
    Platform.CAMERA,
]

DEFAULT_SCAN_INTERVAL = 5
MIN_SCAN_INTERVAL = 2
MAX_SCAN_INTERVAL = 60
CONFIG_SCAN_INTERVAL = 60

CONF_HOST = "host"
CONF_PASSWORD = "password"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_CALENDAR_ENTITY = "calendar_entity"
CONF_WEATHER_ENTITY = "weather_entity"

ATTR_SLEEP_MIN = "sleep_min"
SERVICE_SET_SLEEP_TIMER = "set_sleep_timer"
ATTR_VALUE = "value"
