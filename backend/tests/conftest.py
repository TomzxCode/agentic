import os
import tempfile

import pytest

# Point the app at a throwaway data dir before any app module imports settings.
# Assign unconditionally (not setdefault): under pytest-xdist each worker process
# inherits the controller's environment, so a value the controller set would be
# shared by every worker and they would all write to one SQLite file.
os.environ["AGENTIC_DATA_DIR"] = tempfile.mkdtemp(prefix="agentic-test-")


@pytest.fixture(scope="session", autouse=True)
def _dispose_engine():
    """Close the shared SQLite connection pool so no connections leak at GC."""
    from agentic.db import engine

    yield
    engine.dispose()


@pytest.fixture(autouse=True)
def _reset_queue():
    """Drop the SAQ queue after each test.

    Each async test runs in its own event loop, and a cached aiosqlite connection
    belongs to the loop that opened it, so the queue must be rebuilt per test.
    """
    yield
    from agentic import jobs

    jobs._queue = None


@pytest.fixture(autouse=True)
def _no_github_login_detection(monkeypatch):
    """Keep settings reads deterministic: never shell out to `gh` for the login.

    A test that wants a detected login patches ``detect_github_login`` itself.
    """
    from agentic import settings_store

    monkeypatch.setattr(settings_store, "detect_github_login", lambda: "")
