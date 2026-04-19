"""Test defaults: no Redis/Celery; dummy Google API key before app imports."""
import os

import pytest

# Must run before test modules import app.utils.geocoding (needs key at import time).
os.environ.setdefault("GOOGLE_API_KEY", "test-key-for-unit-tests")


@pytest.fixture(autouse=True)
def _test_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REDIS_URL", raising=False)
