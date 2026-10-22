import re

import structlog

from agentic.log_setup import configure_logging, millisecond_timestamp


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
