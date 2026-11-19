"""Tests for notify.py (pure, no Home Assistant import)."""
from __future__ import annotations

import pytest

import bugne_notify as notify

URL = "http://192.0.2.10:8123/api/webhook/abc"
ACTIONS = [{"id": "yes", "label": "Yes"}, {"id": "no", "label": "No"}]


def test_message_only():
    assert notify.build_payload("Dinner is ready") == {"message": "Dinner is ready"}


def test_full_payload():
    payload = notify.build_payload(
        "Turn off the living room?", title="Home", notif_id="living-1",
        actions=ACTIONS, reply_url=URL,
    )
    assert payload == {
        "message": "Turn off the living room?",
        "title": "Home",
        "id": "living-1",
        "actions": ACTIONS,
        "reply_url": URL,
    }


def test_reply_url_left_out_without_actions():
    assert "reply_url" not in notify.build_payload("Hello", reply_url=URL)


@pytest.mark.parametrize("message", ["", "   ", None])
def test_empty_message_refused(message):
    with pytest.raises(ValueError):
        notify.build_payload(message)


def test_actions_need_a_reply_url():
    with pytest.raises(ValueError):
        notify.build_payload("Hello", actions=ACTIONS)


def test_too_many_actions_refused():
    with pytest.raises(ValueError):
        notify.build_payload("Hello", actions=ACTIONS + [{"id": "x", "label": "X"}], reply_url=URL)


@pytest.mark.parametrize("action", [{"id": "", "label": "Yes"}, {"id": "yes", "label": ""}, {"id": "yes"}])
def test_incomplete_action_refused(action):
    with pytest.raises(ValueError):
        notify.build_payload("Hello", actions=[action], reply_url=URL)


def test_long_text_is_cut_on_a_character_boundary():
    payload = notify.build_payload("é" * 200, title="é" * 40)
    # 255 bytes at most for the message: 127 two-byte characters.
    assert payload["message"] == "é" * 127
    assert payload["title"] == "é" * 23
    assert len(payload["message"].encode()) <= notify.MAX_MESSAGE_BYTES


def test_long_label_is_cut():
    payload = notify.build_payload(
        "Hello", actions=[{"id": "yes", "label": "x" * 40}], reply_url=URL
    )
    assert payload["actions"][0]["label"] == "x" * notify.MAX_LABEL_BYTES


def test_identifiers_are_never_cut():
    # A cut id would come back different from the one the automation waits for.
    with pytest.raises(ValueError):
        notify.build_payload("Hello", notif_id="x" * 48)
    with pytest.raises(ValueError):
        notify.build_payload("Hello", actions=[{"id": "x" * 32, "label": "Yes"}], reply_url=URL)
    with pytest.raises(ValueError):
        notify.build_payload("Hello", actions=ACTIONS, reply_url="http://192.0.2.10/" + "x" * 250)


def test_identifiers_refuse_control_characters():
    # The device turns them into spaces: the id would not come back as sent.
    with pytest.raises(ValueError):
        notify.build_payload("Hello", notif_id="a\tb")
    with pytest.raises(ValueError):
        notify.build_payload("Hello", actions=[{"id": "a\nb", "label": "Yes"}], reply_url=URL)


def test_parse_reply():
    assert notify.parse_reply({"id": "living-1", "action": "yes"}) == ("living-1", "yes")
    assert notify.parse_reply({"action": "yes"}) == ("", "yes")


@pytest.mark.parametrize(
    "data", [None, [], "yes", {}, {"id": "a"}, {"id": "a", "action": ""}, {"id": 3, "action": "yes"},
             {"id": "a", "action": 1}, {"id": "a", "action": "x" * 100}]
)
def test_parse_reply_refuses_garbage(data):
    assert notify.parse_reply(data) is None
