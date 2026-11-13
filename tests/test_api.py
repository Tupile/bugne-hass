"""Tests for custom_components/bugne/api.py.

No Home Assistant dependency: api.py is pure aiohttp (see conftest.py for
how it is loaded standalone).
"""
from __future__ import annotations

import asyncio

import aiohttp
import bugne_api
import pytest
from aioresponses import aioresponses
from aioresponses.core import CallbackResult
from yarl import URL

pytestmark = pytest.mark.asyncio


async def test_basic_auth_header_present_when_password_set(make_client):
    client = make_client(password="secret")
    with aioresponses() as mocked:
        mocked.get("http://192.0.2.50/api/status", payload={"id": "A1B2"})
        await client.get_status()

    request = mocked.requests[("GET", URL("http://192.0.2.50/api/status"))][0]
    auth = request.kwargs.get("auth")
    assert isinstance(auth, aiohttp.BasicAuth)
    assert auth.login == "hass"
    assert auth.password == "secret"


async def test_no_auth_header_when_password_empty(make_client):
    client = make_client(password="")
    with aioresponses() as mocked:
        mocked.get("http://192.0.2.50/api/status", payload={"id": "A1B2"})
        await client.get_status()

    request = mocked.requests[("GET", URL("http://192.0.2.50/api/status"))][0]
    assert request.kwargs.get("auth") is None


async def test_401_raises_auth_error(make_client):
    client = make_client(password="wrong")
    with aioresponses() as mocked:
        mocked.get("http://192.0.2.50/api/status", status=401)
        with pytest.raises(bugne_api.BugneAuthError):
            await client.get_status()


async def test_403_raises_auth_error(make_client):
    client = make_client(password="wrong")
    with aioresponses() as mocked:
        mocked.get("http://192.0.2.50/api/status", status=403)
        with pytest.raises(bugne_api.BugneAuthError):
            await client.get_status()


async def test_timeout_raises_connection_error(make_client):
    client = make_client()
    with aioresponses() as mocked:
        mocked.get("http://192.0.2.50/api/status", exception=asyncio.TimeoutError())
        with pytest.raises(bugne_api.BugneConnectionError):
            await client.get_status()


async def test_connection_error_raises_connection_error(make_client):
    client = make_client()
    with aioresponses() as mocked:
        mocked.get(
            "http://192.0.2.50/api/status",
            exception=aiohttp.ClientConnectionError("refused"),
        )
        with pytest.raises(bugne_api.BugneConnectionError):
            await client.get_status()


async def test_4xx_with_body_raises_refused_error_with_message(make_client):
    # 401/403 are treated as auth errors by this API, so use a different
    # 4xx (409) to exercise the "refused with body" path.
    client = make_client()
    with aioresponses() as mocked:
        mocked.post(
            "http://192.0.2.50/api/playback",
            status=409,
            body="quiet hours: playback is disabled",
        )
        with pytest.raises(bugne_api.BugneRefusedError) as exc_info:
            await client.playback_action("toggle")
        assert exc_info.value.message == "quiet hours: playback is disabled"


async def test_command_posts_accept_plain_text_body(make_client):
    """The firmware replies "ok"/"config saved" (text, not JSON) to commands."""
    client = make_client()
    with aioresponses() as mocked:
        mocked.post("http://192.0.2.50/api/playback", body="ok")
        await client.playback_action("volume", value=30)
        mocked.post("http://192.0.2.50/api/config", body="config saved")
        await client.post_config({"schema_version": 1})


async def test_bad_json_raises_protocol_error(make_client):
    client = make_client()
    with aioresponses() as mocked:
        mocked.get(
            "http://192.0.2.50/api/status",
            body="not json",
            content_type="application/json",
        )
        with pytest.raises(bugne_api.BugneProtocolError):
            await client.get_status()


async def test_mutate_config_posts_full_mutated_doc(make_client):
    client = make_client()
    original = {
        "schema_version": 1,
        "ui": {"game": 0, "volume_max": 80},
        "webradios": [],
    }

    def mutator(doc):
        doc["ui"]["game"] = 1

    with aioresponses() as mocked:
        mocked.get("http://192.0.2.50/api/config", payload=original)
        mocked.post("http://192.0.2.50/api/config", payload={})
        result = await client.mutate_config(mutator)

    assert result["ui"]["game"] == 1
    assert result["webradios"] == []

    post_request = mocked.requests[("POST", URL("http://192.0.2.50/api/config"))][0]
    assert post_request.kwargs["json"]["ui"]["game"] == 1
    assert post_request.kwargs["json"]["schema_version"] == 1


async def test_mutate_config_refuses_on_schema_mismatch(make_client):
    client = make_client()
    stale = {"schema_version": 2, "ui": {}}

    def mutator(doc):
        doc["ui"]["game"] = 1

    with aioresponses() as mocked:
        mocked.get("http://192.0.2.50/api/config", payload=stale)
        with pytest.raises(bugne_api.BugneProtocolError):
            await client.mutate_config(mutator)


async def test_lock_serializes_concurrent_requests(make_client):
    """No two requests should be in flight on the client at the same time."""
    client = make_client()
    in_flight = 0
    max_in_flight = 0

    async def slow_status(url, **kwargs):
        nonlocal in_flight, max_in_flight
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)
        await asyncio.sleep(0.05)
        in_flight -= 1
        return CallbackResult(status=200, payload={"id": "A1B2"})

    with aioresponses() as mocked:
        mocked.get(
            "http://192.0.2.50/api/status", callback=slow_status, repeat=True
        )
        await asyncio.gather(client.get_status(), client.get_status())

    assert max_in_flight == 1


async def test_post_agenda_sends_payload_and_accepts_plain_text(make_client):
    client = make_client()
    payload = {"weather": {"cond": "sunny", "temp": "12 °C"}, "events": []}
    with aioresponses() as mocked:
        mocked.post("http://192.0.2.50/api/agenda", body="ok")
        await client.post_agenda(payload)
    request = mocked.requests[("POST", URL("http://192.0.2.50/api/agenda"))][0]
    assert request.kwargs["json"] == payload
