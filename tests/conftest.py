"""Shared pytest fixtures."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from waterwatch.store import reset_store_for_tests  # noqa: E402


@pytest.fixture(autouse=True)
def temp_store(tmp_path):
    """Bind a fresh local JSON store per test so complaints don't leak between tests."""
    reset_store_for_tests(tmp_path / "store.json")
    yield


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from waterwatch.main import app

    return TestClient(app)


@pytest.fixture
def orchestrator():
    from waterwatch.agents import get_orchestrator

    return get_orchestrator()
