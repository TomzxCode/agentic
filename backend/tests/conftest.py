import os
import tempfile

import pytest

# Point the app at a throwaway data dir before any app module imports settings.
os.environ.setdefault("AGENTIC_DATA_DIR", tempfile.mkdtemp(prefix="agentic-test-"))


@pytest.fixture(scope="session", autouse=True)
def _dispose_engine():
    """Close the shared SQLite connection pool so no connections leak at GC."""
    from agentic.db import engine

    yield
    engine.dispose()
