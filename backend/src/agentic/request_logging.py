"""Send Uvicorn access records through the application's structlog logger."""

import logging

import structlog

log = structlog.get_logger(__name__)


class AccessLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        log.info(record.getMessage())


def configure_request_logging() -> None:
    """Replace Uvicorn's formatter in each server process, including reloads."""
    logger = logging.getLogger("uvicorn.access")
    logger.handlers = [AccessLogHandler()]
    logger.propagate = False
