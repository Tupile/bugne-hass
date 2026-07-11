"""Shared pytest fixtures for the Bugne API tests.

These tests exercise custom_components/bugne/api.py directly, which has no
Home Assistant dependency, so they can run in a plain aiohttp environment.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import aiohttp
import pytest

# Load api.py directly by file path, NOT via `custom_components.bugne.api`:
# importing the `custom_components.bugne` package would run its __init__.py,
# which imports Home Assistant. api.py itself has zero HA imports, so it can
# be loaded standalone. Registered in sys.modules so test modules can just
# `import bugne_api` (conftest.py is always loaded before test collection).
_API_PATH = Path(__file__).resolve().parents[1] / "custom_components" / "bugne" / "api.py"
_spec = importlib.util.spec_from_file_location("bugne_api", _API_PATH)
bugne_api = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(bugne_api)
sys.modules["bugne_api"] = bugne_api


@pytest.fixture
def host() -> str:
    return "192.0.2.50"


@pytest.fixture
async def session():
    async with aiohttp.ClientSession() as session:
        yield session


@pytest.fixture
def make_client(session):
    def _make(password: str = "") -> bugne_api.BugneApiClient:
        return bugne_api.BugneApiClient("192.0.2.50", password, session)

    return _make
