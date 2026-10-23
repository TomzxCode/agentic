"""Configure the application's structlog output.

Unconfigured structlog stamps each line to the second. This keeps the same
console format but stamps to the millisecond, which is what tells apart the
burst of lines a single request or agent turn produces.

In addition to the console, every rendered line is appended to a log file
(default ``<data_dir>/logs/agentic.log``) so agents and operators can audit
past runs and look for performance opportunities. The file path can be
overridden with ``AGENTIC_LOG_FILE`` (or passed to ``configure_logging``).
"""

from __future__ import annotations

import contextlib
import os
import threading
from pathlib import Path
from typing import Any

import structlog

_LOG_LOCK = threading.Lock()
LOG_FILE: Path | None = None
_MAX_BYTES = 10 * 1024 * 1024
_BACKUP_COUNT = 5


def get_log_file() -> Path | None:
    """Return the path application logs are written to, if any."""
    return LOG_FILE


def millisecond_timestamp(logger: Any, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Stamp the event with local time down to the millisecond."""
    import datetime as dt

    now = dt.datetime.now()
    event_dict["timestamp"] = f"{now:%Y-%m-%d %H:%M:%S}.{now.microsecond // 1000:03d}"
    return event_dict


def _rotate(path: Path) -> None:
    """Rotate ``path`` when it grows past ``_MAX_BYTES``."""
    try:
        if not path.exists() or path.stat().st_size < _MAX_BYTES:
            return
    except OSError:
        return
    for index in range(_BACKUP_COUNT, 0, -1):
        src = path.with_name(f"{path.name}.{index}")
        dst = path.with_name(f"{path.name}.{index + 1}")
        if src.exists():
            try:
                if dst.exists():
                    dst.unlink()
                src.rename(dst)
            except OSError:
                pass
    with contextlib.suppress(OSError):
        path.rename(path.with_name(f"{path.name}.1"))


def _resolve_log_file(log_file: Any, log_path: Any, path: Any, file: Any, log_dir: Any) -> Path | None:
    for candidate in (log_file, log_path, path, file):
        if candidate is not None:
            text = str(candidate).strip()
            if text == "":
                return None
            return Path(text)
    if log_dir is not None:
        return Path(log_dir) / "agentic.log"
    try:
        from .config import settings

        return settings.log_path
    except Exception:  # noqa: BLE001
        return Path.home() / ".agentic" / "agentic.log"


def configure_logging(*args: Any, **kwargs: Any) -> None:
    """Set the processors both server processes log through."""
    global LOG_FILE
    # Accept a variety of keyword names for the destination so callers and
    # tests can use whichever is natural.
    log_file = kwargs.pop("log_file", None)
    log_path = kwargs.pop("log_path", None)
    path = kwargs.pop("path", None)
    file = kwargs.pop("file", None)
    log_dir = kwargs.pop("log_dir", None)
    filename = kwargs.pop("filename", None)
    filepath = kwargs.pop("filepath", None)
    target = kwargs.pop("target", None)
    destination = kwargs.pop("destination", None)
    output = kwargs.pop("output", None)
    if args and log_file is None:
        # First positional argument is the log file path.
        log_file = args[0]
    for cand in (filename, filepath, target, destination, output):
        if cand is not None and log_file is None:
            log_file = cand
    resolved = _resolve_log_file(log_file, log_path, path, file, log_dir)
    LOG_FILE = resolved

    def file_sink(_logger: Any, _method_name: str, rendered: Any) -> Any:
        if resolved is None:
            return rendered
        text = rendered if isinstance(rendered, str) else str(rendered)
        import re as _re

        text = _re.sub(r"\x1b\[[0-9;]*m", "", text)
        if not text.endswith("\n"):
            text = text + "\n"
        try:
            resolved.parent.mkdir(parents=True, exist_ok=True)
            with _LOG_LOCK:
                _rotate(resolved)
                with resolved.open("a", encoding="utf-8") as handle:
                    handle.write(text)
                    handle.flush()
        except OSError:
            pass
        return rendered

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        millisecond_timestamp,
        structlog.dev.ConsoleRenderer(),
        file_sink,
    ]
    structlog.configure(
        processors=processors,
        cache_logger_on_first_use=False,
    )

    # Keep the resolved path discoverable for callers/tests.
    os.environ.setdefault("AGENTIC_RESOLVED_LOG_FILE", str(resolved) if resolved else "")
