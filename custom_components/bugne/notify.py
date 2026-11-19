"""Notifications shown on the device screen, with up to two answer buttons.

Pure module: no Home Assistant import, so it is unit-tested on its own.

Home Assistant posts the notification to the device (POST /api/notify). The
device posts the chosen answer back to a webhook as {"id": ..., "action": ...}.
The limits below are the device's buffer sizes minus the terminator, in UTF-8
bytes.
"""
from __future__ import annotations

from typing import Any

MAX_ACTIONS = 2
MAX_ID_BYTES = 47
MAX_TITLE_BYTES = 47
MAX_MESSAGE_BYTES = 255
MAX_ACTION_ID_BYTES = 31
MAX_LABEL_BYTES = 23
MAX_URL_BYTES = 255


def _cut(text: str, max_bytes: int) -> str:
    """Cut text to max_bytes of UTF-8, on a character boundary."""
    return text.encode()[:max_bytes].decode(errors="ignore")


def _exact(text: str, max_bytes: int, what: str) -> str:
    """Refuse a value the device would change: it must come back unchanged.

    The device cuts at max_bytes and turns control characters into spaces.
    """
    if len(text.encode()) > max_bytes:
        raise ValueError(f"{what} is longer than {max_bytes} bytes")
    if any(ord(c) < 0x20 or ord(c) == 0x7F for c in text):
        raise ValueError(f"{what} has a control character")
    return text


def build_payload(
    message: str | None,
    title: str | None = None,
    notif_id: str | None = None,
    actions: list[dict[str, Any]] | None = None,
    reply_url: str | None = None,
) -> dict[str, Any]:
    """Build the body of POST /api/notify. Raises ValueError on bad input."""
    message = (message or "").strip()
    if not message:
        raise ValueError("the message is empty")
    payload: dict[str, Any] = {"message": _cut(message, MAX_MESSAGE_BYTES)}
    if title:
        payload["title"] = _cut(title, MAX_TITLE_BYTES)
    if notif_id:
        payload["id"] = _exact(notif_id, MAX_ID_BYTES, "the notification id")
    if actions:
        if len(actions) > MAX_ACTIONS:
            raise ValueError(f"at most {MAX_ACTIONS} actions")
        if not reply_url:
            raise ValueError("actions need a reply URL")
        out = []
        for action in actions:
            action_id = str(action.get("id") or "")
            label = str(action.get("label") or "")
            if not action_id or not label:
                raise ValueError("every action needs an id and a label")
            out.append(
                {
                    "id": _exact(action_id, MAX_ACTION_ID_BYTES, "an action id"),
                    "label": _cut(label, MAX_LABEL_BYTES),
                }
            )
        payload["actions"] = out
        payload["reply_url"] = _exact(reply_url, MAX_URL_BYTES, "the reply URL")
    return payload


def parse_reply(data: Any) -> tuple[str, str] | None:
    """Read the answer posted by the device. None when it is not one."""
    if not isinstance(data, dict):
        return None
    action = data.get("action")
    notif_id = data.get("id", "")
    if not isinstance(action, str) or not isinstance(notif_id, str):
        return None
    if not action or len(action.encode()) > MAX_ACTION_ID_BYTES:
        return None
    if len(notif_id.encode()) > MAX_ID_BYTES:
        return None
    return notif_id, action
