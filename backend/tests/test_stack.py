import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete as sa_delete
from sqlmodel import Session

from agentic.db import create_db_and_tables, engine
from agentic.main import app
from agentic.models import (
    AgentEvent,
    AgentRun,
    Association,
    Change,
    ChangeIntervention,
    StackEntry,
    Task,
    TaskPerson,
    TaskRepository,
    TaskSession,
    TimelineEvent,
    Worktree,
)


def _clear(session: Session) -> None:
    """Drop every task (and its children) plus the stack, in FK-safe order.

    The stack is materialized from the in-flight tasks, so each test needs a
    database with no tasks at all to assert exact stacks.
    """
    for model in (
        AgentEvent,
        AgentRun,
        Association,
        ChangeIntervention,
        Change,
        Worktree,
        TimelineEvent,
        TaskRepository,
        TaskPerson,
        TaskSession,
        StackEntry,
        Task,
    ):
        session.exec(sa_delete(model))
    session.commit()


@pytest.fixture(autouse=True)
def _clean_stack():
    """Each stack test starts from an empty stack and no tasks (shared DB)."""
    create_db_and_tables()
    with Session(engine) as session:
        _clear(session)
    yield
    with Session(engine) as session:
        _clear(session)


def _push(client: TestClient, title: str, position: str = "top") -> list[dict]:
    response = client.post("/api/stack", json={"title": title, "position": position})
    assert response.status_code == 201, response.text
    return response.json()


def _titles(entries: list[dict]) -> list[str]:
    return [entry["task"]["title"] for entry in entries]


def test_push_positions_and_current():
    with TestClient(app) as client:
        stack = _push(client, "first")
        assert _titles(stack) == ["first"]
        assert stack[0]["is_current"] is True
        assert stack[0]["position"] == 0
        assert stack[0]["execution_count"] == 1
        assert stack[0]["started_at"] is not None

        # "next" inserts right after the current task.
        stack = _push(client, "next", position="next")
        assert _titles(stack) == ["first", "next"]
        assert [entry["position"] for entry in stack] == [0, 1]
        assert [entry["is_current"] for entry in stack] == [True, False]

        # "last" appends.
        stack = _push(client, "last", position="last")
        assert _titles(stack) == ["first", "next", "last"]

        # "top" becomes the new current task.
        stack = _push(client, "top")
        assert _titles(stack) == ["top", "first", "next", "last"]
        assert stack[0]["is_current"] is True
        assert stack[1]["is_current"] is False


def test_empty_stack_push_next_becomes_current():
    with TestClient(app) as client:
        stack = _push(client, "only", position="next")
        assert _titles(stack) == ["only"]
        assert stack[0]["is_current"] is True


def test_pop_marks_done_and_promotes_next():
    with TestClient(app) as client:
        _push(client, "a")
        _push(client, "b")

        popped = client.post("/api/stack/pop").json()
        assert _titles(popped) == ["a"]
        assert popped[0]["is_current"] is True

        # The popped task is done and kept in history.
        history = client.get("/api/stack/history").json()
        assert _titles(history) == ["b"]
        assert history[0]["deleted_at"] is not None
        assert history[0]["is_current"] is False
        task = client.get(f"/api/tasks/{history[0]['task_id']}").json()
        assert task["status"] == "done"

        assert client.post("/api/stack/pop").json() == []
        assert client.post("/api/stack/pop").json() == []


def test_reorder_and_promote_track_current_and_sessions():
    with TestClient(app) as client:
        _push(client, "a")
        _push(client, "b")
        _push(client, "c")
        stack = client.get("/api/stack").json()
        assert _titles(stack) == ["c", "b", "a"]

        # Move the last entry (a) to position 1.
        moved = client.post("/api/stack/reorder", json={"entry_id": stack[2]["id"], "position": 1}).json()
        assert _titles(moved) == ["c", "a", "b"]
        assert [entry["position"] for entry in moved] == [0, 1, 2]

        # Promote b to the top: it becomes current again (it was current once
        # when it was pushed) and starts a new session.
        b_id = next(entry["id"] for entry in moved if entry["task"]["title"] == "b")
        promoted = client.post(f"/api/stack/{b_id}/promote").json()
        assert _titles(promoted) == ["b", "c", "a"]
        b = promoted[0]
        assert b["is_current"] is True
        assert b["execution_count"] == 2

        # Re-promote c then b again so b has three sessions.
        c_id = next(entry["id"] for entry in promoted if entry["task"]["title"] == "c")
        client.post(f"/api/stack/{c_id}/promote")
        promoted = client.post(f"/api/stack/{b_id}/promote").json()
        b = promoted[0]
        assert b["execution_count"] == 3
        assert b["duration"] >= 0


def test_remove_soft_deletes_without_status_change():
    with TestClient(app) as client:
        _push(client, "a")
        _push(client, "b")
        stack = client.get("/api/stack").json()
        a = next(entry for entry in stack if entry["task"]["title"] == "a")

        assert client.delete(f"/api/stack/{a['id']}").status_code == 204
        remaining = client.get("/api/stack").json()
        assert _titles(remaining) == ["b"]
        # Removing the non-current task leaves b current and its status untouched.
        assert remaining[0]["is_current"] is True
        task = client.get(f"/api/tasks/{a['task_id']}").json()
        assert task["status"] == "open"

        assert client.delete("/api/stack/nope").status_code == 404


def test_push_existing_task_is_already_on_the_stack():
    with TestClient(app) as client:
        task = client.post("/api/tasks", json={"title": "existing"}).json()
        # It is materialized onto the stack automatically.
        assert _titles(client.get("/api/stack").json()) == ["existing"]

        duplicate = client.post("/api/stack", json={"task_id": task["id"]})
        assert duplicate.status_code == 409

        missing = client.post("/api/stack", json={"task_id": "nope"})
        assert missing.status_code == 404


def test_inflight_tasks_join_the_stack_automatically():
    with TestClient(app) as client:
        client.post("/api/tasks", json={"title": "Open task"})
        client.post("/api/tasks", json={"title": "In progress", "status": "in_progress"})
        client.post("/api/tasks", json={"title": "Blocked", "status": "blocked"})
        client.post("/api/tasks", json={"title": "Done task", "status": "done"})
        client.post("/api/tasks", json={"title": "Archived task", "status": "archived"})

        stack = client.get("/api/stack").json()
        titles = {entry["task"]["title"] for entry in stack}
        assert titles == {"Open task", "In progress", "Blocked"}
        assert sum(1 for entry in stack if entry["is_current"]) == 1

        # A task that leaves the in-flight statuses leaves the stack on the
        # next read.
        open_task = next(entry for entry in stack if entry["task"]["title"] == "Open task")
        client.patch(f"/api/tasks/{open_task['task_id']}", json={"status": "done"})
        titles = {entry["task"]["title"] for entry in client.get("/api/stack").json()}
        assert "Open task" not in titles
        assert titles == {"In progress", "Blocked"}


def test_new_inflight_task_joins_at_the_bottom():
    with TestClient(app) as client:
        client.post("/api/tasks", json={"title": "First"})
        assert _titles(client.get("/api/stack").json()) == ["First"]

        client.post("/api/tasks", json={"title": "Second"})
        # The existing order is kept; the new task lands at the bottom.
        assert _titles(client.get("/api/stack").json()) == ["First", "Second"]

        client.post("/api/tasks", json={"title": "Third"})
        assert _titles(client.get("/api/stack").json()) == ["First", "Second", "Third"]


def test_removed_task_stays_off_the_stack_until_pushed():
    with TestClient(app) as client:
        task = client.post("/api/tasks", json={"title": "Keep me off"}).json()
        entry = next(entry for entry in client.get("/api/stack").json() if entry["task_id"] == task["id"])

        assert client.delete(f"/api/stack/{entry['id']}").status_code == 204
        assert "Keep me off" not in _titles(client.get("/api/stack").json())

        # Pushing it again brings it back.
        pushed = client.post("/api/stack", json={"task_id": task["id"]})
        assert pushed.status_code == 201
        assert "Keep me off" in _titles(client.get("/api/stack").json())


def test_update_entry_edits_the_task():
    with TestClient(app) as client:
        _push(client, "before")
        entry = client.get("/api/stack").json()[0]
        updated = client.patch(f"/api/stack/{entry['id']}", json={"title": "after", "description": "note"}).json()
        assert updated[0]["task"]["title"] == "after"
        assert updated[0]["task"]["description"] == "note"

        # A blank title is rejected (kept as-is), and an unknown entry is a no-op.
        unchanged = client.patch(f"/api/stack/{entry['id']}", json={"title": "  "}).json()
        assert unchanged[0]["task"]["title"] == "after"


def test_current_endpoint():
    with TestClient(app) as client:
        assert client.get("/api/stack/current").json() is None
        _push(client, "a")
        _push(client, "b")
        current = client.get("/api/stack/current").json()
        assert current["task"]["title"] == "b"


def test_deleting_task_removes_its_stack_entries():
    with TestClient(app) as client:
        _push(client, "a")
        _push(client, "b")
        stack = client.get("/api/stack").json()
        a = next(entry for entry in stack if entry["task"]["title"] == "a")

        assert client.delete(f"/api/tasks/{a['task_id']}").status_code == 204
        remaining = client.get("/api/stack").json()
        assert _titles(remaining) == ["b"]
        assert all(entry["task_id"] != a["task_id"] for entry in remaining)


def test_push_requires_a_title():
    with TestClient(app) as client:
        response = client.post("/api/stack", json={"title": "   "})
        assert response.status_code == 400
