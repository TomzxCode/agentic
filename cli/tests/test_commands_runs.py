"""Run waiting/streaming and session commands."""

from _helpers import FakeClient

from agentic_cli import cli
from agentic_cli.commands import runs as runs_cmd


def test_run_wait_polls_until_terminal(monkeypatch, text_format):
    runs = iter(
        [
            {"id": "r1", "status": "running", "kind": "chat", "prompt": "p"},
            {"id": "r1", "status": "succeeded", "kind": "chat", "prompt": "p"},
        ]
    )

    class Polling:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get_run(self, run_id):
            return next(runs)

    monkeypatch.setattr(cli.runtime, "_client", lambda: Polling())
    monkeypatch.setattr(cli.time, "sleep", lambda seconds: None)
    assert "succeeded" in runs_cmd.run_wait("r1", timeout=600, interval=0)


def test_run_wait_times_out(monkeypatch, text_format):
    class Stuck:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get_run(self, run_id):
            return {"id": "r1", "status": "running", "kind": "chat", "prompt": "p"}

    monkeypatch.setattr(cli.runtime, "_client", lambda: Stuck())
    times = iter([0, 0, 1000])
    monkeypatch.setattr(cli.time, "monotonic", lambda: next(times))
    monkeypatch.setattr(cli.time, "sleep", lambda seconds: None)
    assert "still running" in runs_cmd.run_wait("r1", timeout=10, interval=0)


def test_run_stream_prints_until_finished(monkeypatch, capsys, text_format):
    monkeypatch.setattr(cli.runtime, "_client", FakeClient)
    runs_cmd.run_stream("r1")
    assert "[message] hi" in capsys.readouterr().out


def test_session_commands(text_format, fake_client):
    assert "ses_1" in runs_cmd.session_list("t1")
    text = runs_cmd.session_get("t1", "s1")
    assert "harness: opencode" in text and "cwd: /w" in text
    assert "attached session s2" in runs_cmd.session_add("t1", "ses_2", label="second")
    assert "updated session s1" in runs_cmd.session_update("t1", "s1", label="renamed")
    assert "removed session s1" in runs_cmd.session_remove("t1", "s1")
