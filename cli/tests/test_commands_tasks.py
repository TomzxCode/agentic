"""Task commands: deadlines, create/update forwarding, detail, and dependencies."""

from _helpers import FakeClient

from agentic_cli import cli
from agentic_cli.commands import tasks


def test_task_deadlines_lists_soonest_with_due(text_format, fake_client):
    out = tasks.task_deadlines(within_days=3)
    assert "t1" in out
    assert "due 2026-01-02 00:00" in out


def test_task_create_forwards_deadline(text_format, monkeypatch):
    seen: dict = {}

    class Recorder(FakeClient):
        def create_task(self, **fields):
            seen.update(fields)
            return {"id": "t9", "title": "T"}

    monkeypatch.setattr(cli.runtime, "_client", Recorder)
    tasks.task_create(title="T", deadline="2026-02-01T09:00:00")
    assert seen["deadline"] == "2026-02-01T09:00:00"


def test_task_update_can_clear_deadline(text_format, monkeypatch):
    calls: dict = {}

    class Recorder(FakeClient):
        def update_task(self, task_id, **fields):
            calls["update"] = fields
            return {"id": task_id, "status": "open", "priority": 1, "title": "T"}

        def set_task_deadline(self, task_id, deadline):
            calls["clear"] = (task_id, deadline)
            return {"id": task_id, "status": "open", "priority": 1, "title": "T"}

    monkeypatch.setattr(cli.runtime, "_client", Recorder)
    tasks.task_update("t1", clear_deadline=True)
    assert calls["clear"] == ("t1", None)


def test_task_create_forwards_waiting_and_snooze(text_format, monkeypatch):
    seen: dict = {}

    class Recorder(FakeClient):
        def create_task(self, **fields):
            seen.update(fields)
            return {"id": "t9", "title": "T"}

    monkeypatch.setattr(cli.runtime, "_client", Recorder)
    tasks.task_create(
        title="T",
        waiting_on="p1",
        follow_up="2026-02-01T09:00:00",
        snooze="2026-02-02T09:00:00",
    )
    assert seen["waiting_on_person_id"] == "p1"
    assert seen["follow_up_at"] == "2026-02-01T09:00:00"
    assert seen["snoozed_until"] == "2026-02-02T09:00:00"


def test_task_update_can_clear_waiting_and_snooze(text_format, monkeypatch):
    calls: dict = {}

    class Recorder(FakeClient):
        def update_task(self, task_id, **fields):
            calls["update"] = fields
            return {"id": task_id, "status": "open", "priority": 1, "title": "T"}

        def set_task_waiting(self, task_id, person_id, follow_up_at=None):
            calls["waiting"] = (task_id, person_id, follow_up_at)
            return {"id": task_id, "status": "open", "priority": 1, "title": "T"}

        def set_task_snooze(self, task_id, snoozed_until):
            calls["snooze"] = (task_id, snoozed_until)
            return {"id": task_id, "status": "open", "priority": 1, "title": "T"}

    monkeypatch.setattr(cli.runtime, "_client", Recorder)
    tasks.task_update("t1", clear_waiting=True, clear_snooze=True)
    assert calls["waiting"] == ("t1", None, None)
    assert calls["snooze"] == ("t1", None)


def test_task_create_forwards_slack_url(text_format, monkeypatch):
    seen: dict = {}

    class Recorder(FakeClient):
        def create_task(self, **fields):
            seen.update(fields)
            return {"id": "t9", "title": fields.get("title") or "Slack thread"}

    monkeypatch.setattr(cli.runtime, "_client", Recorder)
    out = tasks.task_create(slack_url="https://acme.slack.com/archives/C1/p2")
    assert seen["slack_url"] == "https://acme.slack.com/archives/C1/p2"
    assert "created t9" in out


def test_task_get_shows_recorded_sessions(text_format, monkeypatch):
    class WithSessions(FakeClient):
        def get_task(self, task_id):
            return {
                "id": task_id,
                "status": "open",
                "priority": 1,
                "title": "T",
                "sessions": [{"id": "s1", "session_id": "ses_1"}],
            }

    monkeypatch.setattr(cli.runtime, "_client", WithSessions)
    assert "session: ses_1 (s1)" in tasks.task_get("t1")


def test_dependency_and_graph_commands(text_format, fake_client):
    deps = tasks.task_deps("t1")
    assert "before:" in deps and "First" in deps
    assert "related:" in deps and "Sibling" in deps
    assert "Next" in tasks.task_link("t1", "t2")
    assert "unlinked t2 from t1" in tasks.task_unlink("t1", "t2")
    graph = tasks.graph()
    assert "nodes: 2  edges: 1" in graph and "t1 -> t2" in graph
