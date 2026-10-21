import logging

from structlog.testing import capture_logs

from agentic.request_logging import AccessLogHandler, configure_request_logging


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
