import logging

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from structlog.testing import capture_logs

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
