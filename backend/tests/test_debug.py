import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from structlog.testing import capture_logs

from agentic import debug
from agentic.log_setup import configure_logging


def test_request_ids_are_unique_and_stable_across_snapshots(monkeypatch):
    monkeypatch.setattr(debug, "_recent_requests", [])
    app = FastAPI()
    app.add_middleware(debug.DebugMiddleware)

    @app.get("/api/tasks")
    def tasks():
        return []

    @app.get("/api/debug/requests")
    def requests():
        return debug.recent_requests()

    with TestClient(app) as client:
        client.get("/api/tasks")
        first = client.get("/api/debug/requests").json()
        client.get("/api/tasks")
        second = client.get("/api/debug/requests").json()
        assert len(second) == 2
        assert first[0]["id"] == second[1]["id"]
        assert second[0]["id"] != second[1]["id"]


def test_the_breakdown_logs_a_separate_debug_line_per_component():
    before = debug._debug_state.get()
    configure_logging(level="debug")
    try:
        debug.start_request("GET", "/api/reviews")
        with debug.phase("review store"):
            with debug.phase("review store view", aggregate=True):
                pass
            with debug.phase("review store view", aggregate=True):
                pass
        debug.record_cli_call(["ghx", "pr", "view", "42", "--repo", "o/r"], 210.0, exit_code=0)
        debug.record_cli_call(["ghx", "pr", "view", "43", "--repo", "o/r"], 5.0, exit_code=0)
        debug.record_query("select 1", 2.5)

        with capture_logs() as logs:
            debug.log_breakdown()
    finally:
        debug._debug_state.set(before)
        configure_logging(level="info")

    phases = [entry for entry in logs if entry["event"] == "request phase"]
    assert [entry["phase"] for entry in phases] == ["review store", "review store view"]
    assert phases[0]["log_level"] == "debug"
    assert phases[0]["path"] == "/api/reviews"
    assert phases[0]["duration_ms"] >= 0
    assert "calls" not in phases[0]
    # The two views fold into one line that says how many ran.
    assert phases[1]["calls"] == 2

    db = next(entry for entry in logs if entry["event"] == "request db")
    assert db["queries"] == 1
    assert db["time_ms"] == 2.5

    tools = next(entry for entry in logs if entry["event"] == "request tools")
    assert tools["calls"] == 2
    assert tools["time_ms"] == 215.0
    assert tools["slowest"] == "ghx pr view 42 --repo o/r (210.0ms)"


def test_an_aggregate_phase_still_lets_a_failure_through():
    before = debug._debug_state.get()
    try:
        debug.start_request("GET", "/api/reviews")
        with pytest.raises(ValueError, match="boom"), debug.phase("review store reports", aggregate=True):
            raise ValueError("boom")
        state = debug._debug_state.get()
        assert state is not None
        phases = state["phases"]
        assert len(phases) == 1
        assert phases[0]["name"] == "review store reports"
        assert phases[0]["calls"] == 1
    finally:
        debug._debug_state.set(before)


def test_the_breakdown_is_silent_outside_a_request():
    before = debug._debug_state.get()
    configure_logging(level="debug")
    try:
        debug._debug_state.set(None)
        assert debug._debug_state.get() is None
        with capture_logs() as logs:
            debug.log_breakdown()
            # A phase outside a request is a no-op, not an error.
            with debug.phase("background"):
                pass
    finally:
        debug._debug_state.set(before)
        configure_logging(level="info")

    assert logs == []
