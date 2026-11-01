"""Execution graph commands: the trigger lists their flags build."""

import json

import pytest

from agentic_cli.commands import graphs


def test_shortcut_triggers_builds_schedule_and_webhook():
    assert graphs._shortcut_triggers("0 9 * * *", "Europe/Paris", False) == [
        {"type": "schedule", "config": {"cron": "0 9 * * *", "timezone": "Europe/Paris"}}
    ]
    # An empty schedule adds nothing, so the flags can clear the triggers.
    assert graphs._shortcut_triggers("", None, False) == []
    assert graphs._shortcut_triggers(None, None, True) == [{"type": "webhook", "config": {}}]


def test_load_triggers_reads_a_list(tmp_path):
    path = tmp_path / "triggers.json"
    path.write_text(json.dumps([{"type": "webhook", "config": {"secret": "x"}}]))
    assert graphs._load_triggers(str(path)) == [{"type": "webhook", "config": {"secret": "x"}}]

    path.write_text(json.dumps({"type": "webhook"}))
    with pytest.raises(ValueError):
        graphs._load_triggers(str(path))
