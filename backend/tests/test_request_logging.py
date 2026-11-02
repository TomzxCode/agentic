import logging

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from structlog.testing import capture_logs

from agentic import debug
from agentic.log_setup import configure_logging
from agentic.request_logging import AccessLogHandler, RequestErrorMiddleware, configure_request_logging


def test_access_log_uses_structlog(monkeypatch):
    logger = logging.getLogger("uvicorn.access")
    monkeypatch.setattr(logger, "handlers", [])
    monkeypatch.setattr(logger, "propagate", True)
    monkeypatch.setattr(logger, "level", logging.INFO)
    configure_request_logging()
    configure_request_logging()

    with capture_logs() as logs:
        logger.info('%s - "%s %s HTTP/%s" %d', "127.0.0.1:52361", "GET", "/api/debug/requests", "1.1", 200)

    assert logs == [
        {
            "event": '127.0.0.1:52361 - "GET /api/debug/requests HTTP/1.1" 200',
            "log_level": "info",
        }
    ]
    assert len(logger.handlers) == 1
    assert isinstance(logger.handlers[0], AccessLogHandler)
    assert logger.propagate is False


def test_the_access_line_carries_the_request_duration(monkeypatch):
    logger = logging.getLogger("uvicorn.access")
    monkeypatch.setattr(logger, "handlers", [])
    monkeypatch.setattr(logger, "propagate", True)
    monkeypatch.setattr(logger, "level", logging.INFO)

    # Stand in for Uvicorn, which writes its access line while the response
    # starts, inside the middleware that times the request.
    app = FastAPI()
    app.add_middleware(RequestErrorMiddleware)

    @app.get("/api/timed")
    def timed() -> dict:
        logger.info('%s - "%s %s HTTP/%s" %d', "127.0.0.1:52361", "GET", "/api/timed", "1.1", 200)
        return {"ok": True}

    configure_request_logging()
    client = TestClient(app)
    with capture_logs() as logs:
        assert client.get("/api/timed").status_code == 200

    access = [entry for entry in logs if entry["event"].startswith("127.0.0.1:52361")]
    assert len(access) == 1
    assert isinstance(access[0]["duration_ms"], float)
    assert access[0]["duration_ms"] >= 0


def test_each_timing_gets_its_own_debug_line(monkeypatch):
    logger = logging.getLogger("uvicorn.access")
    monkeypatch.setattr(logger, "handlers", [])
    monkeypatch.setattr(logger, "propagate", True)
    monkeypatch.setattr(logger, "level", logging.INFO)
    configure_logging(level="debug")

    # The debug middleware is added last, so it is the outermost one: its state
    # is set before the middleware that writes the access line runs.
    app = FastAPI()
    app.add_middleware(RequestErrorMiddleware)
    app.add_middleware(debug.DebugMiddleware)

    @app.get("/api/slow")
    def slow() -> dict:
        with debug.phase("github enrich"):
            debug.record_cli_call(["ghx", "pr", "view", "42", "--repo", "o/r"], 210.0)
        logger.info('%s - "%s %s HTTP/%s" %d', "127.0.0.1:52361", "GET", "/api/slow", "1.1", 200)
        return {"ok": True}

    configure_request_logging()
    try:
        client = TestClient(app)
        with capture_logs() as logs:
            assert client.get("/api/slow").status_code == 200
    finally:
        configure_logging(level="info")

    access = next(entry for entry in logs if entry["event"].startswith("127.0.0.1:52361"))
    # The access line stays short: the timings are their own lines below it.
    assert set(access) == {"event", "log_level", "duration_ms"}

    phase = next(entry for entry in logs if entry["event"] == "request phase")
    assert phase["log_level"] == "debug"
    assert phase["path"] == "/api/slow"
    assert phase["phase"] == "github enrich"
    assert phase["duration_ms"] >= 0

    tools = next(entry for entry in logs if entry["event"] == "request tools")
    assert tools["log_level"] == "debug"
    assert tools["calls"] == 1
    assert tools["time_ms"] == 210.0
    assert tools["slowest"] == "ghx pr view 42 --repo o/r (210.0ms)"


def test_no_breakdown_lines_at_info_level(monkeypatch):
    logger = logging.getLogger("uvicorn.access")
    monkeypatch.setattr(logger, "handlers", [])
    monkeypatch.setattr(logger, "propagate", True)
    monkeypatch.setattr(logger, "level", logging.INFO)
    configure_logging(level="info")

    app = FastAPI()
    app.add_middleware(RequestErrorMiddleware)
    app.add_middleware(debug.DebugMiddleware)

    @app.get("/api/quiet")
    def quiet() -> dict:
        debug.record_cli_call(["ghx", "pr", "view", "42"], 210.0)
        logger.info('%s - "%s %s HTTP/%s" %d', "127.0.0.1:52361", "GET", "/api/quiet", "1.1", 200)
        return {"ok": True}

    configure_request_logging()
    client = TestClient(app)
    with capture_logs() as logs:
        assert client.get("/api/quiet").status_code == 200

    access = [entry for entry in logs if entry["event"].startswith("127.0.0.1:52361")]
    assert len(access) == 1
    assert set(access[0]) == {"event", "log_level", "duration_ms"}
    assert [entry for entry in logs if entry["event"].startswith("request ")] == []


def _error_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestErrorMiddleware)

    @app.get("/api/ok")
    def ok() -> dict:
        return {"ok": True}

    @app.post("/api/items/abc/poke")
    def poke() -> None:
        raise HTTPException(status_code=400, detail="No person carries the GitHub login @ghost.")

    @app.get("/api/boom")
    def boom() -> None:
        raise HTTPException(status_code=500, detail="kaboom")

    @app.post("/api/validated")
    def validated(count: int) -> dict:
        return {"count": count}

    @app.get("/api/text")
    def text() -> None:
        raise HTTPException(status_code=409, detail="Line one\n  line two")

    return app


def test_a_failed_request_logs_its_status_and_detail():
    client = TestClient(_error_app())
    with capture_logs() as logs:
        response = client.post("/api/items/abc/poke")

    assert response.status_code == 400
    assert response.json() == {"detail": "No person carries the GitHub login @ghost."}
    failed = [entry for entry in logs if entry["event"] == "request failed"]
    assert len(failed) == 1
    entry = failed[0]
    assert entry["log_level"] == "warning"
    assert entry["method"] == "POST"
    assert entry["path"] == "/api/items/abc/poke"
    assert entry["status"] == 400
    assert entry["detail"] == "No person carries the GitHub login @ghost."
    assert isinstance(entry["duration_ms"], float)


def test_a_successful_request_logs_nothing():
    client = TestClient(_error_app())
    with capture_logs() as logs:
        client.get("/api/ok")
    assert [entry for entry in logs if entry["event"] == "request failed"] == []


def test_a_server_error_logs_at_error_level():
    client = TestClient(_error_app())
    with capture_logs() as logs:
        client.get("/api/boom")
    entry = next(entry for entry in logs if entry["event"] == "request failed")
    assert entry["log_level"] == "error"
    assert entry["detail"] == "kaboom"


def test_a_validation_error_names_the_field():
    client = TestClient(_error_app())
    with capture_logs() as logs:
        client.post("/api/validated", json={})
    entry = next(entry for entry in logs if entry["event"] == "request failed")
    assert entry["status"] == 422
    assert "count" in entry["detail"]


def test_a_multi_line_detail_stays_one_line():
    client = TestClient(_error_app())
    with capture_logs() as logs:
        client.get("/api/text")
    entry = next(entry for entry in logs if entry["event"] == "request failed")
    assert entry["detail"] == "Line one line two"
