"""HTTP client for the Bugne device API.

This module is pure aiohttp and imports nothing from Home Assistant, so it
can be unit tested without HA installed.
"""
from __future__ import annotations

import asyncio
from typing import Any, Callable

import aiohttp

#: Schema version of /api/config this client understands. Defined here (not
#: only in const.py) so tests can import it without pulling in const.py's
#: Home-Assistant-flavoured constants.
SUPPORTED_SCHEMA_VERSION = 1

DEFAULT_TIMEOUT = 10
SCREENSHOT_TIMEOUT = 30
GHOTA_CHECK_TIMEOUT = 30


class BugneError(Exception):
    """Base error for all Bugne API failures."""


class BugneAuthError(BugneError):
    """Raised on HTTP 401/403 (wrong or missing password)."""


class BugneConnectionError(BugneError):
    """Raised when the device cannot be reached (connect/timeout/DNS)."""


class BugneRefusedError(BugneError):
    """Raised when the device refuses a request with a 4xx and a message.

    Example: quiet hours refusing playback, or a refresh already running.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class BugneProtocolError(BugneError):
    """Raised when the device response cannot be parsed as expected."""


class BugneApiClient:
    """Thin async client for the Bugne local HTTP API.

    All requests are serialized through a single lock because the device
    only accepts a handful of concurrent sockets.
    """

    def __init__(self, host: str, password: str, session: aiohttp.ClientSession) -> None:
        self._host = host
        self._password = password
        self._session = session
        self._lock = asyncio.Lock()

    @property
    def host(self) -> str:
        return self._host

    def _url(self, path: str) -> str:
        return f"http://{self._host}{path}"

    def _auth(self) -> aiohttp.BasicAuth | None:
        if not self._password:
            return None
        return aiohttp.BasicAuth("hass", self._password)

    async def _do_request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        timeout: int = DEFAULT_TIMEOUT,
        expect_json: bool = True,
    ) -> Any:
        """Perform one HTTP request. Caller is responsible for locking."""
        try:
            async with self._session.request(
                method,
                self._url(path),
                json=json,
                auth=self._auth(),
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                if resp.status in (401, 403):
                    raise BugneAuthError(f"authentication failed ({resp.status})")
                if 400 <= resp.status < 500:
                    text = (await resp.text()).strip()
                    raise BugneRefusedError(text or f"request refused ({resp.status})")
                resp.raise_for_status()
                if not expect_json:
                    return await resp.read()
                try:
                    return await resp.json(content_type=None)
                except (aiohttp.ContentTypeError, ValueError) as err:
                    raise BugneProtocolError(f"invalid JSON response: {err}") from err
        except (BugneAuthError, BugneRefusedError, BugneProtocolError):
            raise
        except (asyncio.TimeoutError, aiohttp.ClientConnectionError) as err:
            raise BugneConnectionError(str(err)) from err
        except aiohttp.ClientError as err:
            raise BugneConnectionError(str(err)) from err

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Perform one HTTP request under the shared lock."""
        async with self._lock:
            return await self._do_request(method, path, **kwargs)

    # -- status / playback -------------------------------------------------

    async def get_status(self) -> dict[str, Any]:
        return await self._request("GET", "/api/status")

    async def get_playback(self) -> dict[str, Any]:
        return await self._request("GET", "/api/playback")

    async def playback_action(
        self, action: str, value: Any = None, title: str | None = None
    ) -> None:
        payload: dict[str, Any] = {"action": action}
        if value is not None:
            payload["value"] = value
        if title is not None:
            payload["title"] = title
        # Command endpoints reply with plain text ("ok"), not JSON.
        await self._request("POST", "/api/playback", json=payload, expect_json=False)

    # -- config --------------------------------------------------------------

    async def get_config(self) -> dict[str, Any]:
        return await self._request("GET", "/api/config")

    async def post_config(self, doc: dict[str, Any]) -> None:
        # Replies with plain text ("config saved"), not JSON.
        await self._request("POST", "/api/config", json=doc, expect_json=False)

    async def mutate_config(
        self, mutator: Callable[[dict[str, Any]], None]
    ) -> dict[str, Any]:
        """Read-modify-write the config document under one held lock.

        Fetches a fresh copy, checks the schema version, applies `mutator`
        in place, and POSTs the full document back. Returns the mutated
        document.
        """
        async with self._lock:
            doc = await self._do_request("GET", "/api/config")
            if doc.get("schema_version") != SUPPORTED_SCHEMA_VERSION:
                raise BugneProtocolError(
                    "unsupported config schema_version: "
                    f"{doc.get('schema_version')!r}"
                )
            mutator(doc)
            await self._do_request("POST", "/api/config", json=doc, expect_json=False)
            return doc

    # -- ghota (GitHub OTA) ----------------------------------------------

    async def get_ghota_status(self) -> dict[str, Any]:
        return await self._request("GET", "/api/ghota/status")

    async def ghota_check(self) -> dict[str, Any]:
        return await self._request("GET", "/api/ghota/check", timeout=GHOTA_CHECK_TIMEOUT)

    async def ghota_install(self) -> None:
        await self._request("POST", "/api/ghota", expect_json=False)

    # -- podcasts ----------------------------------------------------------

    async def podcasts_refresh(self) -> None:
        await self._request("POST", "/api/podcasts/refresh", expect_json=False)

    async def get_podcasts_refreshing(self) -> dict[str, Any]:
        return await self._request("GET", "/api/podcasts/refresh")

    # -- misc ----------------------------------------------------------------

    async def get_screenshot(self) -> bytes:
        return await self._request(
            "GET", "/api/screenshot", timeout=SCREENSHOT_TIMEOUT, expect_json=False
        )

    async def reboot(self) -> None:
        await self._request("POST", "/api/reboot", expect_json=False)
