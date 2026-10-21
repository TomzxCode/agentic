"""Waiting-on and snooze: parking a task off the stack until its date."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete as sa_delete
from sqlmodel import Session

from agentic.db import create_db_and_tables, engine
from agentic.main import app
from agentic.models.tasks import StackEntry, Task, TaskSession, TimelineEvent


def _clear(session: Session) -> None:
    """Drop every task (and its stack rows) so each stack read is deterministic."""
    for model in (TimelineEvent, TaskSession, StackEntry, Task):
        session.exec(sa_delete(model))
    session.commit()


@pytest.fixture(autouse=True)
def _clean_tasks():
    create_db_and_tables()
    with Session(engine) as session:
        _clear(session)
    yield
    with Session(engine) as session:
        _clear(session)


def _person(client: TestClient, name: str = "Ada") -> dict:
    response = client.post("/api/people", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()


def _task(client: TestClient, title: str = "Waiting task") -> dict:
    response = client.post("/api/tasks", json={"title": title})
    assert response.status_code == 201, response.text
    return response.json()


def _stack_ids(client: TestClient) -> list[str]:
    return [entry["task_id"] for entry in client.get("/api/stack").json()]


def _future(**over) -> str:
    return (datetime.now(UTC) + timedelta(**over)).isoformat()


def test_waiting_parks_the_task_until_the_follow_up():
    with TestClient(app) as client:
        person = _person(client)
        task = _task(client)
        assert task["status"] == "open"
        assert task["id"] in _stack_ids(client)

        updated = client.patch(
            f"/api/tasks/{task['id']}",
            json={"waiting_on_person_id": person["id"], "follow_up_at": _future(days=2)},
        ).json()
        # Waiting marks the task blocked and names the person.
        assert updated["status"] == "blocked"
        assert updated["waiting_on_person_id"] == person["id"]
        assert updated["waiting_on_name"] == "Ada"
        assert updated["follow_up_at"] is not None

        # It leaves the stack but is not "removed" history.
        assert task["id"] not in _stack_ids(client)
        assert task["id"] not in [entry["task_id"] for entry in client.get("/api/stack/history").json()]

        # The follow-up passing brings it back on the next stack read.
        client.patch(
            f"/api/tasks/{task['id']}",
            json={"follow_up_at": _future(minutes=-1)},
        )
        assert task["id"] in _stack_ids(client)

        # The wait and the status change are recorded.
        events = client.get(f"/api/tasks/{task['id']}/timeline").json()
        event = next(e for e in events if "waiting_on_person_id" in e["data_json"].get("changes", {}))
        assert "status" in event["data_json"]["changes"]


def test_clearing_the_wait_reopens_and_clears_the_follow_up():
    with TestClient(app) as client:
        person = _person(client)
        task = _task(client)
        client.patch(
            f"/api/tasks/{task['id']}",
            json={"waiting_on_person_id": person["id"], "follow_up_at": _future(days=2)},
        )

        cleared = client.patch(
            f"/api/tasks/{task['id']}",
            json={"waiting_on_person_id": None},
        ).json()
        assert cleared["status"] == "open"
        assert cleared["waiting_on_person_id"] is None
        assert cleared["follow_up_at"] is None
        assert task["id"] in _stack_ids(client)


def test_an_explicit_status_wins_over_the_waiting_rule():
    with TestClient(app) as client:
        person = _person(client)
        task = _task(client)
        updated = client.patch(
            f"/api/tasks/{task['id']}",
            json={"waiting_on_person_id": person["id"], "status": "in_progress"},
        ).json()
        assert updated["status"] == "in_progress"


def test_waiting_without_a_follow_up_stays_parked_until_pushed():
    with TestClient(app) as client:
        person = _person(client)
        task = _task(client)
        client.patch(f"/api/tasks/{task['id']}", json={"waiting_on_person_id": person["id"]})
        assert task["id"] not in _stack_ids(client)

        # Pushing is an explicit "work on it now": it clears the wait and reopens.
        pushed = client.post("/api/stack", json={"task_id": task["id"]}).json()
        assert task["id"] in [entry["task_id"] for entry in pushed]
        detail = client.get(f"/api/tasks/{task['id']}").json()
        assert detail["waiting_on_person_id"] is None
        assert detail["follow_up_at"] is None
        assert detail["status"] == "open"


def test_snooze_parks_the_task_without_changing_its_status():
    with TestClient(app) as client:
        task = _task(client)
        assert task["id"] in _stack_ids(client)

        snoozed = client.patch(
            f"/api/tasks/{task['id']}",
            json={"snoozed_until": _future(days=1)},
        ).json()
        assert snoozed["status"] == "open"
        assert snoozed["snoozed_until"] is not None
        assert task["id"] not in _stack_ids(client)

        # A snooze that has come around no longer parks the task.
        client.patch(
            f"/api/tasks/{task['id']}",
            json={"snoozed_until": _future(minutes=-1)},
        )
        assert task["id"] in _stack_ids(client)

        # Clearing it keeps the task where it is.
        cleared = client.patch(f"/api/tasks/{task['id']}", json={"snoozed_until": None}).json()
        assert cleared["snoozed_until"] is None
        assert task["id"] in _stack_ids(client)


def test_deleting_the_waiting_person_clears_the_wait():
    with TestClient(app) as client:
        person = _person(client)
        task = _task(client)
        client.patch(
            f"/api/tasks/{task['id']}",
            json={"waiting_on_person_id": person["id"], "follow_up_at": _future(days=1)},
        )

        assert client.delete(f"/api/people/{person['id']}").status_code == 204
        detail = client.get(f"/api/tasks/{task['id']}").json()
        assert detail["waiting_on_person_id"] is None
        assert detail["follow_up_at"] is None


def test_naive_snooze_and_follow_up_are_treated_as_utc():
    with TestClient(app) as client:
        person = _person(client)
        task = _task(client)
        updated = client.patch(
            f"/api/tasks/{task['id']}",
            json={
                "waiting_on_person_id": person["id"],
                "follow_up_at": "2030-02-01T09:00:00",
                "snoozed_until": "2030-02-02T09:00:00",
            },
        ).json()
        assert updated["follow_up_at"].startswith("2030-02-01T09:00:00")
        assert updated["snoozed_until"].startswith("2030-02-02T09:00:00")
