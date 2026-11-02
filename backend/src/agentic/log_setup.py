"""Configure the application's structlog output.

Unconfigured structlog stamps each line to the second. This keeps the same
console format but stamps to the millisecond, which is what tells apart the
burst of lines a single request or agent turn produces.

In addition to the console, every rendered line is appended to a log file
(default ``<data_dir>/logs/agentic.log``) so agents and operators can audit
past runs and look for performance opportunities. The file path can be
overridden with ``AGENTIC_LOG_FILE`` (or passed to ``configure_logging``).
The level comes from ``AGENTIC_LOG_LEVEL`` (default ``info``); ``debug`` also
logs the per-request timing breakdown as separate lines.
"""

from __future__ import annotations

import contextlib
import logging
import os
import re
import threading
from pathlib import Path
from typing import Any, BinaryIO

import structlog

_LOG_LOCK = threading.Lock()
LOG_FILE: Path | None = None
#: The level the logger filters at, so a caller can tell whether a debug-only
#: detail (the request breakdown on the access line) is wanted.
LOG_LEVEL: int = logging.INFO
_MAX_BYTES = 10 * 1024 * 1024
_BACKUP_COUNT = 5
#: How many bytes may be written before the file's real size is checked again.
#: Tracking the size in memory keeps the common write down to one syscall.
_CHECK_INTERVAL = 64 * 1024
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")


def get_log_file() -> Path | None:
    """Return the path application logs are written to, if any."""
    return LOG_FILE


def debug_enabled() -> bool:
    """Whether the logger is configured to emit debug details."""
    return LOG_LEVEL <= logging.DEBUG


def level_value(level: str | int | None) -> int:
    """A level name ("debug", "warning") or number as logging's level number."""
    if isinstance(level, int):
        return level
    text = str(level or "").strip().upper()
    if not text:
        return logging.INFO
    return logging.getLevelNamesMapping().get(text, logging.INFO)


def millisecond_timestamp(logger: Any, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Stamp the event with local time down to the millisecond."""
    import datetime as dt

    now = dt.datetime.now()
    event_dict["timestamp"] = f"{now:%Y-%m-%d %H:%M:%S}.{now.microsecond // 1000:03d}"
    return event_dict


def _rotate_files(path: Path) -> None:
    """Shift ``path`` and its backups, so ``path`` can start empty again."""
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


class _LogFile:
    """One append handle kept open across lines, rotated by tracked size.

    Opening, writing and closing per line costs a stat, an open, a write and a
    close each time, and holds the shared lock for all of it. The handle stays
    open instead, and the size that decides rotation is tracked in memory. The
    file's real size is checked every ``_CHECK_INTERVAL`` bytes, which is also
    when a file rotated by another process (a second server sharing the data
    directory) is noticed: its inode differs from the open handle's, so the
    sink reopens the current path rather than appending to the backup.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._handle: BinaryIO | None = None
        self._size = 0
        self._unchecked = 0

    def close(self) -> None:
        """Close the handle; the next write reopens the path."""
        handle, self._handle = self._handle, None
        self._size = 0
        self._unchecked = 0
        if handle is not None:
            with contextlib.suppress(OSError):
                handle.close()

    def write(self, text: str) -> None:
        """Append one rendered line, rotating first when it would pass the cap."""
        data = text.encode("utf-8", "replace")
        try:
            if self._handle is None:
                self._open()
            if self._unchecked >= _CHECK_INTERVAL:
                self._recheck()
                if self._handle is None:
                    self._open()
            if self._size + len(data) > _MAX_BYTES:
                self._rotate()
            if self._handle is None:
                return
            self._handle.write(data)
            self._handle.flush()
        except (OSError, ValueError):
            self.close()
            return
        self._size += len(data)
        self._unchecked += len(data)

    def _open(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("ab")
        self._handle = handle
        self._size = os.fstat(handle.fileno()).st_size

    def _recheck(self) -> None:
        handle = self._handle
        self._unchecked = 0
        if handle is None:
            return
        try:
            open_stat = os.fstat(handle.fileno())
            current = self.path.stat()
        except OSError:
            self.close()
            return
        if (open_stat.st_dev, open_stat.st_ino) != (current.st_dev, current.st_ino):
            # Another process rotated it; follow the current path.
            self.close()
            with contextlib.suppress(OSError):
                self._open()
            return
        self._size = current.st_size

    def _rotate(self) -> None:
        self.close()
        _rotate_files(self.path)
        with contextlib.suppress(OSError):
            self._open()


#: The sink lines are appended through, kept so a reconfigure reuses its handle.
_SINK: _LogFile | None = None


def _settings_level() -> str:
    """The configured log level, read lazily so this module has no settings import."""
    try:
        from .config import settings

        return settings.log_level
    except Exception:  # noqa: BLE001
        return "info"


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
    global LOG_FILE, LOG_LEVEL, _SINK
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
    level = kwargs.pop("log_level", None)
    if level is None:
        level = kwargs.pop("level", None)
    if args and log_file is None:
        # First positional argument is the log file path.
        log_file = args[0]
    for cand in (filename, filepath, target, destination, output):
        if cand is not None and log_file is None:
            log_file = cand
    resolved = _resolve_log_file(log_file, log_path, path, file, log_dir)
    LOG_FILE = resolved
    if level is None:
        level = _settings_level()
    LOG_LEVEL = level_value(level)

    if _SINK is not None and _SINK.path != resolved:
        _SINK.close()
        _SINK = None
    if resolved is not None and _SINK is None:
        _SINK = _LogFile(resolved)
    sink = _SINK

    def file_sink(_logger: Any, _method_name: str, rendered: Any) -> Any:
        if sink is None:
            return rendered
        text = rendered if isinstance(rendered, str) else str(rendered)
        text = _ANSI_ESCAPE.sub("", text)
        if not text.endswith("\n"):
            text = text + "\n"
        with _LOG_LOCK:
            sink.write(text)
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
        wrapper_class=structlog.make_filtering_bound_logger(LOG_LEVEL),
        cache_logger_on_first_use=False,
    )

    # Keep the resolved path discoverable for callers/tests.
    os.environ.setdefault("AGENTIC_RESOLVED_LOG_FILE", str(resolved) if resolved else "")
