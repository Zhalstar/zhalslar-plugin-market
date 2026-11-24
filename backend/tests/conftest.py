"""Isolated backend test configuration."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

TEST_DATABASE = Path(__file__).parent / "test-market.db"
if TEST_DATABASE.exists():
    TEST_DATABASE.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DATABASE.as_posix()}"
os.environ["AUTH_SECRET_KEY"] = "test-secret-key-with-sufficient-entropy"

from app.database import engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client() -> TestClient:
    """Provide one initialized API client for the test session.

    Yields:
        FastAPI test client.
    """
    with TestClient(app) as test_client:
        yield test_client
    engine.dispose()
    if TEST_DATABASE.exists():
        TEST_DATABASE.unlink()
