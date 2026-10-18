"""Harnesses and agent-run endpoints, including SSE replay and cwd resolution."""

import threading
import time

from fastapi.testclient import TestClient
from sqlmodel import Session

from agentic.agents.runner import persist_event
from agentic.config import settings
from agentic.db import create_db_and_tables, engine
from agentic.main import app
from agentic.models.agents import AgentRun
from agentic.models.base import RunStatus, utcnow
from agentic.models.tasks import Task
from agentic.routers import agent_runs as agents_router
from agentic.routers import agent_streams
from agentic.routers import worktrees as worktrees_router


async def _no_enqueue(run_id: str) -> None:
    """Skip the queue write; tests never start a worker."""
    return None


def test_list_harnesses_reports_availability_and_a_single_default():
    with TestClient(app) as client:
        statuses = client.get("/api/harnesses").json()
        assert {status["id"] for status in statuses} >= {"opencode", "opencode2", "pi"}
        assert all("available" in status and "detail" in status for status in statuses)
        # Exactly one harness is the default.
        assert sum(1 for status in statuses if status["is_default"]) == 1

        full = client.get("/api/harnesses/full").json()
        assert any(harness["command"] for harness in full)


def test_harness_reports_the_default_model_its_config_file_names(tmp_path):
    config = tmp_path / "opencode.json"
    config.write_text('{"model": "zai-coding-plan/glm-5.3-flash"}')
    with TestClient(app) as client:
        created = client.post(
            "/api/harnesses",
            json={"name": "Config", "command": "config-acp", "default_model_source": f"{config}#model"},
        ).json()
        harness_id = created["id"]
        assert created["default_model"] == "zai-coding-plan/glm-5.3-flash"

        full = {harness["id"]: harness for harness in client.get("/api/harnesses/full").json()}
        assert full[harness_id]["default_model"] == "zai-coding-plan/glm-5.3-flash"
        statuses = {status["id"]: status for status in client.get("/api/harnesses").json()}
        assert statuses[harness_id]["default_model"] == "zai-coding-plan/glm-5.3-flash"

        # An override on the harness wins; the detected default stays readable.
        updated = client.patch(f"/api/harnesses/{harness_id}", json={"model": "openai/gpt-5"}).json()
        assert updated["model"] == "openai/gpt-5"
        assert updated["default_model"] == "zai-coding-plan/glm-5.3-flash"

        assert client.delete(f"/api/harnesses/{harness_id}").status_code == 204


def test_setting_a_default_harness_demotes_the_others():
    with TestClient(app) as client:
        before = client.get("/api/harnesses").json()
        current = next(status["id"] for status in before if status["is_default"])
        other = next(status["id"] for status in before if not status["is_default"])

        updated = client.patch(f"/api/harnesses/{other}", json={"is_default": True})
        assert updated.json()["is_default"] is True

        after = {status["id"]: status["is_default"] for status in client.get("/api/harnesses").json()}
        assert after[other] is True
        assert after[current] is False
        assert sum(after.values()) == 1

        client.patch(f"/api/harnesses/{current}", json={"is_default": True})


def test_harness_crud_and_delete_detaches_task():
    with TestClient(app) as client:
        created = client.post("/api/harnesses", json={"name": "Custom", "command": "custom-acp", "args": ["--x"]})
        assert created.status_code == 201
        harness_id = created.json()["id"]

        task = client.post("/api/tasks", json={"title": "T", "harness_id": harness_id}).json()
        assert task["harness_id"] == harness_id

        updated = client.patch(f"/api/harnesses/{harness_id}", json={"model": "gpt-x"})
        assert updated.json()["model"] == "gpt-x"
        assert client.patch("/api/harnesses/missing", json={"name": "x"}).status_code == 404

        assert client.delete(f"/api/harnesses/{harness_id}").status_code == 204
        # The task's reference is cleared rather than left dangling.
        assert client.get(f"/api/tasks/{task['id']}").json()["harness_id"] is None
        assert client.delete("/api/harnesses/missing").status_code == 404

        client.delete(f"/api/tasks/{task['id']}")


def test_create_run_dispatches_and_records_timeline(monkeypatch, tmp_path):
    enqueued: list = []

    async def record(run_id: str) -> None:
        enqueued.append(run_id)

    monkeypatch.setattr(agents_router, "enqueue_run", record)
    with TestClient(app) as client:
        repo_dir = tmp_path / "repo"
        (repo_dir / ".git").mkdir(parents=True)
        repo = client.post("/api/repositories", json={"path": str(repo_dir)}).json()
        task = client.post("/api/tasks", json={"title": "R", "repository_ids": [repo["id"]]}).json()

        assert client.post(f"/api/tasks/{task['id']}/runs", json={"prompt": "   "}).status_code == 400

        run = client.post(f"/api/tasks/{task['id']}/runs", json={"prompt": "do it"}).json()
        assert run["status"] == "queued"
        assert run["cwd"] == str(repo_dir)  # resolved from the task's repository
        assert enqueued == [run["id"]]

        listed = client.get(f"/api/tasks/{task['id']}/runs").json()
        assert any(item["id"] == run["id"] for item in listed)
        assert client.get(f"/api/runs/{run['id']}").json()["id"] == run["id"]
        assert client.get("/api/runs/missing").status_code == 404
        assert client.get(f"/api/runs/{run['id']}/events").json() == []

        assert client.post(f"/api/runs/{run['id']}/cancel").status_code == 200
        assert client.get(f"/api/runs/{run['id']}").json()["status"] == "cancelled"
        assert client.post("/api/runs/missing/cancel").status_code == 404

        timeline = client.get(f"/api/tasks/{task['id']}/timeline").json()
        assert any(event["type"] == "run_started" for event in timeline)

        client.delete(f"/api/tasks/{task['id']}")
        client.delete(f"/api/repositories/{repo['id']}")


def test_create_run_resolves_cwd_variants(monkeypatch, tmp_path):
    monkeypatch.setattr(agents_router, "enqueue_run", _no_enqueue)
    with TestClient(app) as client:
        task = client.post("/api/tasks", json={"title": "C"}).json()

        # An explicit cwd wins.
        run = client.post(f"/api/tasks/{task['id']}/runs", json={"prompt": "x", "cwd": str(tmp_path)}).json()
        assert run["cwd"] == str(tmp_path)

        # With no worktree or repository, the worktree root is the fallback.
        fallback = client.post(f"/api/tasks/{task['id']}/runs", json={"prompt": "x"}).json()
        assert fallback["cwd"] == str(settings.worktree_root)

        # An unknown worktree id is rejected.
        assert (
            client.post(f"/api/tasks/{task['id']}/runs", json={"prompt": "x", "worktree_id": "nope"}).status_code == 404
        )

        client.delete(f"/api/tasks/{task['id']}")


def test_create_run_uses_a_worktree(monkeypatch, tmp_path):
    monkeypatch.setattr(agents_router, "enqueue_run", _no_enqueue)
    monkeypatch.setattr(worktrees_router, "create_worktree", lambda *args, **kwargs: None)
    with TestClient(app) as client:
        repo_dir = tmp_path / "repo"
        (repo_dir / ".git").mkdir(parents=True)
        repo = client.post("/api/repositories", json={"path": str(repo_dir)}).json()
        task = client.post("/api/tasks", json={"title": "W", "repository_ids": [repo["id"]]}).json()
        worktree = client.post(f"/api/tasks/{task['id']}/worktrees", json={}).json()

        explicit = client.post(
            f"/api/tasks/{task['id']}/runs", json={"prompt": "x", "worktree_id": worktree["id"]}
        ).json()
        assert explicit["cwd"] == worktree["path"]

        # No worktree given: the active one is selected automatically.
        auto = client.post(f"/api/tasks/{task['id']}/runs", json={"prompt": "x"}).json()
        assert auto["cwd"] == worktree["path"]

        client.delete(f"/api/tasks/{task['id']}")
        client.delete(f"/api/repositories/{repo['id']}")


def test_refresh_context_builds_a_prompt_and_dispatches(monkeypatch, tmp_path):
    monkeypatch.setattr(agents_router, "enqueue_run", _no_enqueue)
    with TestClient(app) as client:
        repo_dir = tmp_path / "repo"
        (repo_dir / ".git").mkdir(parents=True)
        repo = client.post("/api/repositories", json={"path": str(repo_dir)}).json()
        group = client.post("/api/groups", json={"name": "G", "repository_ids": [repo["id"]]}).json()
        task = client.post(
            "/api/tasks",
            json={"title": "Ctx", "description": "desc", "group_id": group["id"], "repository_ids": [repo["id"]]},
        ).json()
        client.post(f"/api/tasks/{task['id']}/items", json={"item": {"content": "a note", "fetch": False}})

        run = client.post(f"/api/tasks/{task['id']}/context/refresh").json()
        assert run["kind"] == "refresh_context"

        detail = client.get(f"/api/tasks/{task['id']}").json()
        assert any(event["type"] == "context_refresh" for event in detail["timeline"])

        preview = client.get(f"/api/tasks/{task['id']}/context").json()
        assert preview["task_id"] == task["id"]
        assert preview["next_steps"] == []

        client.delete(f"/api/tasks/{task['id']}")
        client.delete(f"/api/groups/{group['id']}")
        client.delete(f"/api/repositories/{repo['id']}")


def test_stream_run_reports_a_missing_run():
    with TestClient(app) as client:
        body = client.get("/api/runs/missing/stream").text
    assert "run not found" in body


def test_stream_run_replays_a_finished_run():
    create_db_and_tables()
    with Session(engine) as session:
        task = Task(title="stream")
        session.add(task)
        session.commit()
        session.refresh(task)
        run = AgentRun(task_id=task.id, prompt="p", status=RunStatus.succeeded)
        session.add(run)
        session.commit()
        session.refresh(run)
        persist_event(session, run.id, {"seq": 1, "type": "message", "text": "hello", "data": {}})
        run_id, task_id = run.id, task.id

    with TestClient(app) as client:
        body = client.get(f"/api/runs/{run_id}/stream").text
        assert "hello" in body
        assert "run_finished" in body
        client.delete(f"/api/tasks/{task_id}")


def test_stream_task_rejects_an_unknown_task():
    with TestClient(app) as client:
        assert client.get("/api/tasks/missing/stream").status_code == 404


def test_stored_events_carry_the_payload_under_the_streams_key():
    """A row is rendered from an event's payload, and the stream calls it
    `data`; the stored endpoint has to answer with the same key so a replayed
    run reads the same as a live one."""
    create_db_and_tables()
    with Session(engine) as session:
        task = Task(title="events")
        session.add(task)
        session.commit()
        session.refresh(task)
        run = AgentRun(task_id=task.id, prompt="p", status=RunStatus.succeeded)
        session.add(run)
        session.commit()
        session.refresh(run)
        persist_event(
            session,
            run.id,
            {"seq": 1, "type": "tool_call", "text": "read", "data": {"toolCallId": "c1", "status": "pending"}},
        )
        run_id, task_id = run.id, task.id

    with TestClient(app) as client:
        events = client.get(f"/api/runs/{run_id}/events").json()
        assert events[0]["data"] == {"toolCallId": "c1", "status": "pending"}
        assert "data_json" not in events[0]
        client.delete(f"/api/tasks/{task_id}")


def test_stream_run_delivers_events_written_after_subscribe():
    """A worker runs in another process, so its persisted events must be polled."""
    with TestClient(app) as client:
        task = client.post("/api/tasks", json={"title": "worker stream"}).json()
        # Create the run after startup, so the startup reconcile does not touch it.
        with Session(engine) as session:
            run = AgentRun(task_id=task["id"], prompt="p", status=RunStatus.running)
            session.add(run)
            session.commit()
            session.refresh(run)
            run_id = run.id

        def write_like_a_worker() -> None:
            time.sleep(1.0)
            with Session(engine) as session:
                persist_event(session, run_id, {"seq": 1, "type": "message", "text": "from-worker", "data": {}})
                row = session.get(AgentRun, run_id)
                assert row is not None
                row.status = RunStatus.succeeded
                row.ended_at = utcnow()
                session.add(row)
                session.commit()

        thread = threading.Thread(target=write_like_a_worker)
        thread.start()
        try:
            body = client.get(f"/api/runs/{run_id}/stream").text
        finally:
            thread.join()
        assert "from-worker" in body
        assert "run_finished" in body
        client.delete(f"/api/tasks/{task['id']}")


def test_task_signature_tracks_worker_visible_changes():
    create_db_and_tables()
    with Session(engine) as session:
        task = Task(title="sig")
        session.add(task)
        session.commit()
        session.refresh(task)
        task_id = task.id
        baseline = agent_streams._task_signature(session, task_id)

        # A new run changes the signature.
        session.add(AgentRun(task_id=task_id, prompt="p", status=RunStatus.queued))
        session.commit()
        with_runs = agent_streams._task_signature(session, task_id)
        assert with_runs != baseline

        # So does a rename (what the Slack summary run does).
        task.title = "renamed"
        session.add(task)
        session.commit()
        assert agent_streams._task_signature(session, task_id) != with_runs

    with TestClient(app) as client:
        client.delete(f"/api/tasks/{task_id}")
