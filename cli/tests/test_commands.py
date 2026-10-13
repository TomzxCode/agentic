"""Coverage for the user-facing CLI commands and renderers."""

import json
from types import SimpleNamespace

import pytest

from agentic_cli import cli
from agentic_cli.client import ApiError


@pytest.fixture
def text_format():
    previous = cli.CONTEXT["format"]
    cli.CONTEXT["format"] = "text"
    yield
    cli.CONTEXT["format"] = previous


class FakeClient:
    """A stand-in for AgenticClient returning plausible shapes per method."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def health(self):
        return {"status": "ok", "service": "agentic"}

    def list_tasks(self, status=None, q=None, tags=None):
        return [{"id": "t1", "status": "open", "priority": 1, "title": "T", "tags": ["bug"]}]

    def list_deadlines(self, within_days=7):
        return [
            {
                "id": "t1",
                "status": "open",
                "priority": 1,
                "title": "T",
                "tags": [],
                "deadline": "2026-01-02T00:00:00",
            }
        ]

    def list_tags(self):
        return [{"name": "bug", "count": 1}]

    def list_people(self):
        return [{"id": "p1", "name": "Ada", "task_count": 1, "item_count": 0}]

    def get_person(self, person_id):
        return {
            "id": person_id,
            "name": "Ada",
            "task_count": 1,
            "item_count": 1,
            "aliases": ["ada", "ada@example.com"],
            "notes": "n",
            "task_ids": ["t1"],
            "item_ids": ["i1"],
        }

    def create_person(self, **fields):
        return {"id": "p2", "name": fields.get("name"), "task_count": 0, "item_count": 0}

    def update_person(self, person_id, **fields):
        return {"id": person_id, "name": fields.get("name") or "Ada", "task_count": 0, "item_count": 0}

    def delete_person(self, person_id):
        return None

    def link_person(self, person_id, **kwargs):
        return {"id": person_id, "name": "Ada", "task_count": 1, "item_count": 0}

    def unlink_person(self, person_id, **kwargs):
        return None

    def merge_person(self, source_id, target_id):
        return {"id": target_id, "name": "Grace", "task_count": 1, "item_count": 0}

    def list_changes(self, task_id=None, status=None, change_class=None):
        return [{"id": "c1", "status": "proposed", "change_class": "feature", "title": "C", "human_intervened": False}]

    def get_change(self, change_id):
        return {
            "id": change_id,
            "status": "accepted",
            "change_class": "bugfix",
            "title": "C",
            "human_intervened": True,
            "external_ref": "https://example/pr/1",
            "opened_at": "2026-01-01T00:00:00",
            "accepted_at": "2026-01-02T00:00:00",
            "interventions": [{"kind": "correction", "note": "n"}],
        }

    def create_change(self, **fields):
        return {
            "id": "c2",
            "status": "proposed",
            "change_class": fields.get("change_class"),
            "title": fields.get("title"),
        }

    def transition_change(self, change_id, status):
        return {"id": change_id, "status": status, "change_class": "feature", "title": "C"}

    def add_intervention(self, change_id, kind="other", note=""):
        return {"id": "i1", "kind": kind, "note": note}

    def delete_change(self, change_id):
        return None

    def get_metrics(self, **kwargs):
        return {
            "window_days": 30,
            "observation_days": 14,
            "tolerance": 0.02,
            "metrics": [
                {
                    "label": "Autonomy rate",
                    "value": 0.5,
                    "baseline": 0.2,
                    "delta": 0.3,
                    "direction": "improving",
                    "numerator": 1,
                    "denominator": 2,
                }
            ],
            "counts": {
                "accepted": 2,
                "touchless": 1,
                "reverted": 0,
                "rejected": 0,
                "pending_observation": 0,
                "open": 0,
            },
        }

    def list_baselines(self):
        return [{"metric": "autonomy_rate", "value": 0.2, "captured_at": "2026-01-01T00:00:00"}]

    def set_baseline(self, metric, value, **fields):
        return {"metric": metric, "value": value}

    def delete_baseline(self, metric):
        return None

    def get_task(self, task_id):
        return {
            "id": task_id,
            "status": "open",
            "priority": 1,
            "title": "T",
            "summary": "s",
            "next_steps": [{"text": "a", "done": False}],
        }

    def create_task(self, **fields):
        return {"id": "t2", "title": fields.get("title")}

    def update_task(self, task_id, **fields):
        return {"id": task_id, "status": "open", "priority": 1, "title": "T"}

    def set_task_deadline(self, task_id, deadline):
        return {"id": task_id, "status": "open", "priority": 1, "title": "T", "deadline": deadline}

    def delete_task(self, task_id):
        return None

    def task_timeline(self, task_id):
        return [{"created_at": "2026-01-01T00:00:00", "type": "created", "message": "m"}]

    def associate(self, task_id, **kwargs):
        return {"item": {"id": "i1"}}

    def unassociate(self, task_id, item_id):
        return None

    def list_items(self, source=None):
        return [{"id": "i1", "source": "note", "title": "N"}]

    def get_item(self, item_id):
        return {"id": item_id, "source": "note", "title": "N"}

    def create_item(self, **fields):
        return {"id": "i2", "source": "note", "title": "N"}

    def update_item(self, item_id, **fields):
        return {"id": item_id, "source": "note", "title": "N"}

    def refresh_item(self, item_id):
        return {"id": item_id, "source": "note", "title": "N"}

    def delete_item(self, item_id):
        return None

    def list_repositories(self):
        return [{"id": "r1", "name": "r", "path": "/p"}]

    def add_repository(self, path, name=None):
        return {"id": "r2", "name": "r", "path": path}

    def remove_repository(self, repository_id):
        return None

    def list_harnesses(self, full=False):
        return [{"id": "opencode", "available": True, "detail": "/usr/bin/opencode"}]

    def create_harness(self, **fields):
        return {"id": "h1", "command": fields.get("command")}

    def update_harness(self, harness_id, **fields):
        return {"id": harness_id, "command": "c"}

    def delete_harness(self, harness_id):
        return None

    def list_worktrees(self, task_id):
        return [{"id": "w1", "status": "active", "branch": "b", "path": "/w"}]

    def create_worktree(self, task_id, repository_id=None, branch=None, base=None):
        return {"id": "w2", "branch": "b", "path": "/w"}

    def remove_worktree(self, task_id, worktree_id):
        return None

    def list_runs(self, task_id):
        return [{"id": "r1", "status": "queued", "kind": "chat", "prompt": "p"}]

    def get_run(self, run_id):
        return {
            "id": run_id,
            "status": "succeeded",
            "kind": "chat",
            "prompt": "p",
            "session_id": "s",
            "cwd": "/w",
            "links": [{"label": "L", "url": "u"}],
        }

    def run_events(self, run_id):
        return [{"type": "message", "text": "hi"}]

    def create_run(self, task_id, prompt, **kwargs):
        return {"id": "r3", "status": "queued", "cwd": "/w"}

    def cancel_run(self, run_id):
        return {"id": run_id, "status": "cancelled"}

    def get_context(self, task_id):
        return {"summary": "s", "next_steps": [{"text": "a", "done": True}]}

    def refresh_context(self, task_id):
        return {"id": "r4"}

    def get_settings(self):
        return {"effective": {"openchamber_url": "x"}}

    def update_settings(self, **fields):
        return {"effective": {"openchamber_url": "x"}}

    def stream_run(self, run_id):
        return iter([{"type": "message", "text": "hi"}, {"type": "run_finished", "text": ""}])

    def list_operations(self, client=None, actor=None, limit=100):
        return [
            {
                "id": "o1",
                "method": "POST",
                "path": "/api/tasks",
                "status_code": 201,
                "client": "cli",
                "actor": "agent",
                "created_at": "2026-01-01T00:00:00",
            }
        ]


@pytest.fixture
def fake_client(monkeypatch):
    monkeypatch.setattr(cli, "_client", FakeClient)
    return FakeClient()


def test_renderers():
    task = {
        "id": "t1",
        "status": "open",
        "priority": 2,
        "title": "T",
        "summary": "s",
        "next_steps": [{"text": "a", "done": False}, {"text": "b", "done": True}],
    }
    assert cli._task_line(task).startswith("t1  [open] p2")
    text = cli._task_text(task)
    assert "summary: s" in text and "[ ] a" in text and "[x] b" in text

    assert cli._item_line({"id": "i1", "source": "note", "title": ""}).startswith("i1")
    assert cli._join([], lambda row: "x") == "(none)"

    run = {
        "id": "r1",
        "status": "queued",
        "kind": "chat",
        "prompt": "p",
        "session_id": "s",
        "cwd": "/w",
        "links": [{"label": "L", "command": "c"}],
    }
    assert "queued" in cli._run_line(run)
    run_text = cli._run_text(run)
    assert "session: s" in run_text and "cwd: /w" in run_text and "L: c" in run_text


def test_emit_auto_uses_json_off_a_tty(monkeypatch):
    cli.CONTEXT["format"] = "auto"
    monkeypatch.setattr(cli, "sys", SimpleNamespace(stdout=SimpleNamespace(isatty=lambda: False), stderr=None))
    assert json.loads(cli.emit({"a": 1}, "text")) == {"a": 1}

    monkeypatch.setattr(cli, "sys", SimpleNamespace(stdout=SimpleNamespace(isatty=lambda: True), stderr=None))
    assert cli.emit({"a": 1}, "text") == "text"


def test_safe_handles_api_error_and_interrupt(capsys):
    @cli.safe
    def api_failure():
        raise ApiError(404, "nope")

    assert api_failure() == 1
    err = capsys.readouterr().err
    assert "nope" in err and "HTTP 404" in err

    @cli.safe
    def interrupted():
        raise KeyboardInterrupt

    assert interrupted() == 130


def test_link_add_requires_something_to_link(capsys):
    assert cli.link_add("t1") == 1
    assert "provide --item-id" in capsys.readouterr().err


def test_commands_emit_text(text_format, fake_client):
    assert "ok (agentic)" in cli.health()
    assert "t1" in cli.task_list()
    assert "bug" in cli.tag_list()
    assert "T" in cli.task_get("t1")
    assert "created t2" in cli.task_create(title="New")
    assert "updated t1" in cli.task_update("t1", title="T")
    assert "deleted t1" in cli.task_delete("t1")
    assert "created" in cli.task_timeline("t1")
    assert "linked i1 to t1" in cli.link_add("t1", item_id="i1")
    assert "linked i1 to t1" in cli.link_add("t1", url="u")
    assert "unlinked i1" in cli.link_remove("t1", "i1")
    assert "i1" in cli.item_list()
    assert "N" in cli.item_get("i1")
    assert "created i2" in cli.item_create(content="x")
    assert "refreshed i1" in cli.item_refresh("i1")
    assert "deleted i1" in cli.item_delete("i1")
    assert "r1" in cli.repository_list()
    assert "added r2" in cli.repository_add("/p")
    assert "removed r1" in cli.repository_remove("r1")
    assert "w1" in cli.worktree_list("t1")
    assert "created worktree w2" in cli.worktree_create("t1")
    assert "removed worktree w1" in cli.worktree_remove("t1", "w1")
    assert "r1" in cli.run_list("t1")
    assert "session: s" in cli.run_get("r1")
    assert "[message] hi" in cli.run_events("r1")
    assert "started run r3" in cli.run_create("t1", "p")
    assert "cancelling r1" in cli.run_cancel("r1")
    assert "- [x] a" in cli.context_get("t1")
    assert "context refresh started" in cli.context_refresh("t1")
    assert "opencode" in cli.harness_list()
    assert "created harness h1" in cli.harness_create(name="n", command="c")
    assert "updated harness h1" in cli.harness_update("h1", name="n")
    assert "deleted h1" in cli.harness_delete("h1")
    assert "openchamber_url" in cli.settings_get()
    assert "openchamber_url" in cli.settings_set(openchamber_url="x")


def test_task_deadlines_lists_soonest_with_due(text_format, fake_client):
    out = cli.task_deadlines(within_days=3)
    assert "t1" in out
    assert "due 2026-01-02T00" in out


def test_task_create_forwards_deadline(text_format, monkeypatch):
    seen: dict = {}

    class Recorder(FakeClient):
        def create_task(self, **fields):
            seen.update(fields)
            return {"id": "t9", "title": "T"}

    monkeypatch.setattr(cli, "_client", Recorder)
    cli.task_create(title="T", deadline="2026-02-01T09:00:00")
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

    monkeypatch.setattr(cli, "_client", Recorder)
    cli.task_update("t1", clear_deadline=True)
    assert calls["clear"] == ("t1", None)


def test_task_create_forwards_slack_url(text_format, monkeypatch):
    seen: dict = {}

    class Recorder(FakeClient):
        def create_task(self, **fields):
            seen.update(fields)
            return {"id": "t9", "title": fields.get("title") or "Slack thread"}

    monkeypatch.setattr(cli, "_client", Recorder)
    out = cli.task_create(slack_url="https://acme.slack.com/archives/C1/p2")
    assert seen["slack_url"] == "https://acme.slack.com/archives/C1/p2"
    assert "created t9" in out


def test_change_and_metrics_commands(text_format, fake_client):
    assert "c1" in cli.change_list()
    text = cli.change_get("c1")
    assert "accepted" in text and "intervention [correction]" in text
    assert "created change c2" in cli.change_create("t1", title="C", change_class="bugfix")
    assert "verified: c1" in cli.change_verify("c1")
    assert "accepted: c1" in cli.change_accept("c1")
    assert "rejected: c1" in cli.change_reject("c1")
    assert "reverted: c1" in cli.change_revert("c1")
    assert "intervened (correction) on c1" in cli.change_intervene("c1", kind="correction", note="n")
    assert "deleted c1" in cli.change_delete("c1")
    assert "Autonomy rate" in cli.metrics_show()
    assert "autonomy_rate" in cli.baseline_list()
    assert "baseline = 20.0%" in cli.baseline_set("autonomy_rate", 0.2)
    assert "deleted baseline yield" in cli.baseline_delete("yield")


def test_people_commands(text_format, fake_client, capsys):
    assert "Ada" in cli.person_list()
    text = cli.person_get("p1")
    assert "aliases: ada, ada@example.com" in text and "tasks: t1" in text
    assert "created p2" in cli.person_create(name="Ada")
    assert "updated p1" in cli.person_update("p1", aliases=["ada"])
    assert "deleted p1" in cli.person_delete("p1")
    assert "linked p1 to task t1" in cli.person_link("p1", task="t1")
    assert "linked p1 to item i1" in cli.person_link("p1", item="i1")
    assert "unlinked p1 from task t1" in cli.person_unlink("p1", task="t1")
    assert "merged p1 into p2  Grace" in cli.person_merge("p1", into="p2")
    assert cli.person_link("p1") == 1
    assert "provide --task or --item" in capsys.readouterr().err


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

    monkeypatch.setattr(cli, "_client", lambda: Polling())
    monkeypatch.setattr(cli.time, "sleep", lambda seconds: None)
    assert "succeeded" in cli.run_wait("r1", timeout=600, interval=0)


def test_run_wait_times_out(monkeypatch, text_format):
    class Stuck:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get_run(self, run_id):
            return {"id": "r1", "status": "running", "kind": "chat", "prompt": "p"}

    monkeypatch.setattr(cli, "_client", lambda: Stuck())
    times = iter([0, 0, 1000])
    monkeypatch.setattr(cli.time, "monotonic", lambda: next(times))
    monkeypatch.setattr(cli.time, "sleep", lambda seconds: None)
    assert "still running" in cli.run_wait("r1", timeout=10, interval=0)


def test_run_stream_prints_until_finished(monkeypatch, capsys, text_format):
    monkeypatch.setattr(cli, "_client", FakeClient)
    cli.run_stream("r1")
    assert "[message] hi" in capsys.readouterr().out


def test_operation_list_command(text_format, fake_client):
    text = cli.operation_list()
    assert "POST" in text and "/api/tasks" in text and "cli" in text and "agent" in text
