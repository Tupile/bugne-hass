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

# Notifications: the device posts the chosen answer to a webhook, and the
# integration fires this event with it.
CONF_WEBHOOK_ID = "webhook_id"
EVENT_NOTIFICATION_ACTION = "bugne_notification_action"
SERVICE_SEND_NOTIFICATION = "send_notification"
SERVICE_CLEAR_NOTIFICATION = "clear_notification"
ATTR_MESSAGE = "message"
ATTR_TITLE = "title"
ATTR_ID = "id"
ATTR_ACTIONS = "actions"
ATTR_LABEL = "label"
