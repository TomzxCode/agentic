"""Configure the application's structlog output.

Unconfigured structlog stamps each line to the second. This keeps the same
console format but stamps to the millisecond, which is what tells apart the
burst of lines a single request or agent turn produces.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import structlog


def millisecond_timestamp(logger: Any, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Stamp the event with local time down to the millisecond."""
    now = dt.datetime.now()
    event_dict["timestamp"] = f"{now:%Y-%m-%d %H:%M:%S}.{now.microsecond // 1000:03d}"
    return event_dict


def configure_logging() -> None:
    """Set the processors both server processes log through."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            millisecond_timestamp,
            structlog.dev.ConsoleRenderer(),
        ],
        cache_logger_on_first_use=False,
    )
