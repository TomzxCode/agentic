"""Renderer helpers for tasks, items, runs, sessions, stack, and schedules."""

from agentic_cli import render


def test_renderers():
    task = {
        "id": "t1",
        "status": "open",
        "priority": 2,
        "title": "T",
        "summary": "s",
        "next_steps": [{"text": "a", "done": False}, {"text": "b", "done": True}],
    }
    assert render._task_line(task).startswith("t1  [open] p2")
    text = render._task_text(task)
    assert "summary: s" in text and "[ ] a" in text and "[x] b" in text

    assert render._item_line({"id": "i1", "source": "note", "title": ""}).startswith("i1")
    assert render._join([], lambda row: "x") == "(none)"

    run = {
        "id": "r1",
        "status": "queued",
        "kind": "chat",
        "prompt": "p",
        "model": "zai-coding-plan/glm-5.3",
        "session_id": "s",
        "cwd": "/w",
        "links": [{"label": "L", "command": "c"}],
    }
    assert "queued" in render._run_line(run)
    run_text = render._run_text(run)
    assert "model: zai-coding-plan/glm-5.3" in run_text
    assert "session: s" in run_text and "cwd: /w" in run_text and "L: c" in run_text

    session = {
        "id": "s1",
        "task_id": "t1",
        "session_id": "ses_1",
        "label": "first",
        "harness_id": "opencode",
        "cwd": "/w",
        "links": [{"label": "L", "url": "u"}],
    }
    assert render._session_line(session) == "s1  ses_1  first"
    session_text = render._session_text(session)
    assert "harness: opencode" in session_text and "cwd: /w" in session_text and "L: u" in session_text


def test_stack_renderers():
    entry = {"position": 0, "is_current": True, "task": {"title": "T"}, "execution_count": 2, "duration": 90}
    assert render._stack_line(entry) == "* 0  T  x2  1m 30s"
    assert render._format_duration(0) == "0m 00s"
    assert render._format_duration(3661) == "1h 01m"
    assert render._format_duration(90000) == "1d 01h"
    assert render._format_duration(-5) == "0m 00s"


def test_schedule_renderers():
    task = {
        "id": "s1",
        "name": "Nightly",
        "command": "echo hi",
        "schedule": "0 9 * * *",
        "cwd": "/w",
        "timezone": "Europe/Paris",
        "enabled": True,
        "next_run_at": "2026-01-02T09:00:00Z",
        "last_status": "succeeded",
    }
    assert render._schedule_line(task).startswith("s1  on   0 9 * * *")
    assert "Europe/Paris" in render._schedule_line(task)
    assert "next 2026-01-02 10:00" in render._schedule_line(task)
    text = render._schedule_text(task)
    assert "command: echo hi" in text and "cwd: /w" in text
    paused = {**task, "enabled": False, "next_run_at": None, "last_status": None}
    assert render._schedule_line(paused).startswith("s1  off")

    run = {"id": "r1", "status": "succeeded", "exit_code": 0, "started_at": "2026-01-02T09:00:00", "output": "hi\n"}
    assert render._schedule_run_line(run) == "2026-01-02 09:00:00  succeeded  exit 0  r1"
    assert "hi" in render._schedule_run_text(run)
    named = {**run, "task_name": "Nightly"}
    assert render._schedule_run_text(named).startswith("Nightly  ")
