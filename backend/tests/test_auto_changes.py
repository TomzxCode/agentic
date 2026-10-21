"""Automatic change records for authored, task-linked merged pull requests."""

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import delete as sa_delete
from sqlmodel import Session, col, select

from agentic.auto_changes import AUTO_CHANGE_NOTES, record_merged_pr_changes
from agentic.db import create_db_and_tables, engine
from agentic.main import app
from agentic.models.base import ChangeStatus, TaskStatus
from agentic.models.changes import Change
from agentic.models.items import Association, SourceItem
from agentic.models.tasks import Task, TimelineEvent
from agentic.routers import task_items

MERGED_AT = "2026-01-02T03:04:05+00:00"
MERGED_AT_DT = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


def _pr(number: int = 1, *, state: str = "MERGED", author: str = "me", merged_at: str | None = MERGED_AT) -> SourceItem:
    return SourceItem(
        source="github",
        kind="pull_request",
        title=f"PR {number}",
        url=f"https://github.com/o/r/pull/{number}",
        external_id=f"o/r#{number}",
        metadata_json={"state": state, "merged_at": merged_at if state == "MERGED" else None, "author": author},
    )


def _link(session: Session, task: Task, item: SourceItem) -> None:
    session.add(Association(task_id=task.id, item_id=item.id))
    session.commit()


def _task_with_pr(session: Session, *, status: TaskStatus = TaskStatus.open) -> tuple[Task, SourceItem]:
    task = Task(title="Land the PR", status=status)
    session.add(task)
    session.commit()
    session.refresh(task)
    item = _pr()
    session.add(item)
    session.commit()
    session.refresh(item)
    _link(session, task, item)
    return task, item


def _cleanup(task_ids=(), item_ids=()) -> None:
    with Session(engine) as session:
        for task_id in task_ids:
            session.exec(sa_delete(Change).where(col(Change.task_id) == task_id))
            session.exec(sa_delete(Association).where(col(Association.task_id) == task_id))
            session.exec(sa_delete(TimelineEvent).where(col(TimelineEvent.task_id) == task_id))
            session.exec(sa_delete(Task).where(col(Task.id) == task_id))
        if item_ids:
            session.exec(sa_delete(SourceItem).where(col(SourceItem.id).in_(item_ids)))
        session.commit()


def test_records_an_accepted_change_dated_to_the_merge():
    create_db_and_tables()
    with Session(engine) as session:
        task, item = _task_with_pr(session)
        task_id, item_id = task.id, item.id
        created = record_merged_pr_changes(session, viewer_login="me")

        assert len(created) == 1
        change = created[0]
        assert change.status == ChangeStatus.accepted
        assert change.external_ref == item.url
        assert change.notes == AUTO_CHANGE_NOTES
        assert change.human_intervened is False
        assert change.opened_at == MERGED_AT_DT
        assert change.accepted_at == MERGED_AT_DT

        events = session.exec(select(TimelineEvent).where(TimelineEvent.task_id == task_id)).all()
        assert any(event.type == "change_opened" and event.data_json.get("auto") for event in events)

        # Idempotent: a second pass finds the change already recorded.
        assert record_merged_pr_changes(session, viewer_login="me") == []
    _cleanup([task_id], [item_id])


def test_a_pr_the_viewer_did_not_author_is_left_alone():
    create_db_and_tables()
    with Session(engine) as session:
        task = Task(title="Someone else's PR")
        session.add(task)
        session.commit()
        session.refresh(task)
        task_id = task.id
        item = _pr(author="someone")
        session.add(item)
        session.commit()
        session.refresh(item)
        item_id = item.id
        _link(session, task, item)

        assert record_merged_pr_changes(session, viewer_login="me") == []
    _cleanup([task_id], [item_id])


def test_no_known_login_records_nothing():
    create_db_and_tables()
    with Session(engine) as session:
        task, item = _task_with_pr(session)
        task_id, item_id = task.id, item.id
        assert record_merged_pr_changes(session, viewer_login="") == []
    _cleanup([task_id], [item_id])


def test_an_archived_task_is_left_alone():
    create_db_and_tables()
    with Session(engine) as session:
        task, item = _task_with_pr(session, status=TaskStatus.archived)
        task_id, item_id = task.id, item.id
        assert record_merged_pr_changes(session, viewer_login="me") == []
    _cleanup([task_id], [item_id])


def test_an_open_pr_is_not_recorded():
    create_db_and_tables()
    with Session(engine) as session:
        task = Task(title="Not merged yet")
        session.add(task)
        session.commit()
        session.refresh(task)
        task_id = task.id
        item = _pr(state="OPEN")
        session.add(item)
        session.commit()
        session.refresh(item)
        item_id = item.id
        _link(session, task, item)

        assert record_merged_pr_changes(session, viewer_login="me") == []
    _cleanup([task_id], [item_id])


def test_an_existing_change_suppresses_the_record():
    create_db_and_tables()
    with Session(engine) as session:
        task, item = _task_with_pr(session)
        task_id, item_id = task.id, item.id
        session.add(Change(task_id=task_id, external_ref=item.external_id))
        session.commit()
        assert record_merged_pr_changes(session, viewer_login="me") == []
    _cleanup([task_id], [item_id])


def test_a_pr_on_two_tasks_records_one_change_each():
    create_db_and_tables()
    with Session(engine) as session:
        first = Task(title="First")
        second = Task(title="Second")
        session.add(first)
        session.add(second)
        session.commit()
        session.refresh(first)
        session.refresh(second)
        task_ids = [first.id, second.id]
        item = _pr()
        session.add(item)
        session.commit()
        session.refresh(item)
        item_id = item.id
        _link(session, first, item)
        _link(session, second, item)

        created = record_merged_pr_changes(session, viewer_login="me")
        assert {change.task_id for change in created} == set(task_ids)
    _cleanup(task_ids, [item_id])


def test_item_ids_narrows_the_pass():
    create_db_and_tables()
    with Session(engine) as session:
        task, item = _task_with_pr(session)
        task_id, item_id = task.id, item.id
        other = _pr(9)
        session.add(other)
        session.commit()
        session.refresh(other)
        other_id = other.id
        _link(session, task, other)

        created = record_merged_pr_changes(session, item_ids=[item_id], viewer_login="me")
        assert [change.external_ref for change in created] == [item.url]
    _cleanup([task_id], [item_id, other_id])


def test_linking_a_merged_pr_records_a_change(monkeypatch):
    # The associate endpoint would fetch the PR's people from GitHub; stub it so
    # the test stays offline.
    monkeypatch.setattr(task_items, "_populate_item_people", lambda *args, **kwargs: None)
    with TestClient(app) as client:
        client.patch("/api/settings", json={"github_login": "me"})
        try:
            task = client.post("/api/tasks", json={"title": "Auto record"}).json()
            url = "https://github.com/auto-test/repo/pull/7001"
            associated = client.post(
                f"/api/tasks/{task['id']}/items",
                json={
                    "item": {
                        "url": url,
                        "metadata_json": {"state": "MERGED", "merged_at": MERGED_AT, "author": "me"},
                        "fetch": False,
                    }
                },
            )
            assert associated.status_code == 201
            item_id = associated.json()["item"]["id"]

            changes = client.get("/api/changes", params={"task_id": task["id"]}).json()
            assert len(changes) == 1
            assert changes[0]["status"] == "accepted"
            assert changes[0]["external_ref"] == url

            # The inbox no longer suggests recording what was recorded for the user.
            mine = [s for s in client.get("/api/inbox").json()["suggestions"] if s["task_id"] == task["id"]]
            assert all(s["kind"] != "record_change_merged_pr" for s in mine)

            client.delete(f"/api/tasks/{task['id']}")
            client.delete(f"/api/items/{item_id}")
        finally:
            client.patch("/api/settings", json={"github_login": ""})
