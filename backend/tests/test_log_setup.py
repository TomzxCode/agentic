import re

import structlog

from agentic import log_setup
from agentic.log_setup import configure_logging, debug_enabled, millisecond_timestamp


def test_millisecond_timestamp_has_three_fraction_digits():
    event = millisecond_timestamp(None, "info", {"event": "hello"})

    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}", event["timestamp"])
    assert "event" in event


def test_log_line_shows_milliseconds(capsys):
    configure_logging()
    structlog.get_logger("test").info("hello", answer=1)

    out = capsys.readouterr().out
    plain = re.sub(r"\x1b\[[0-9;]*m", "", out)
    assert re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3} \[info     \] hello", plain)
    assert "answer=1" in plain


def test_debug_level_emits_debug_events_and_enables_the_breakdown(capsys):
    configure_logging(level="debug")
    try:
        assert debug_enabled() is True
        structlog.get_logger("test").debug("debug detail", answer=1)
        assert "debug detail" in capsys.readouterr().out
    finally:
        configure_logging(level="info")

    assert debug_enabled() is False


def _log_lines(count: int, prefix: str = "line") -> None:
    logger = structlog.get_logger("test")
    for index in range(count):
        logger.info(prefix, n=index)


def _close_sink() -> None:
    sink = log_setup._SINK
    if sink is not None:
        sink.close()


def test_lines_are_appended_through_one_open_handle(tmp_path):
    path = tmp_path / "agentic.log"
    configure_logging(log_file=path)
    try:
        _log_lines(200)
        sink = log_setup._SINK
        assert sink is not None
        handle = sink._handle
        assert handle is not None
        _log_lines(5)
        # A fresh open/close per line would replace the handle object.
        assert sink._handle is handle
    finally:
        _close_sink()

    assert len(path.read_text().splitlines()) == 205


def test_file_rotates_past_the_cap(tmp_path, monkeypatch):
    path = tmp_path / "agentic.log"
    monkeypatch.setattr(log_setup, "_MAX_BYTES", 2000)
    configure_logging(log_file=path)
    try:
        _log_lines(50)
    finally:
        _close_sink()

    assert path.with_name("agentic.log.1").exists()
    written = path.read_text()
    for index in range(1, log_setup._BACKUP_COUNT + 2):
        backup = path.with_name(f"agentic.log.{index}")
        if backup.exists():
            written += backup.read_text()
    numbers = [int(value) for value in re.findall(r"n=(\d+)", written)]
    assert sorted(numbers) == list(range(50))


def test_reopens_when_another_process_rotates_the_file(tmp_path, monkeypatch):
    path = tmp_path / "agentic.log"
    monkeypatch.setattr(log_setup, "_CHECK_INTERVAL", 1)
    configure_logging(log_file=path)
    logger = structlog.get_logger("test")
    try:
        logger.info("first")
        moved = path.with_name("agentic.log.1")
        path.rename(moved)
        logger.info("second")
    finally:
        _close_sink()

    assert "second" in path.read_text()
    assert "second" not in moved.read_text()
