"""Scheduled shell tasks: CRUD, run-now, and the cron scheduler."""

import asyncio
import time
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete as sa_delete
from sqlmodel import Session, col, select

from agentic import schedules
from agentic.db import create_db_and_tables, engine
from agentic.main import app
from agentic.models import ScheduledRunStatus, ScheduledTask, ScheduledTaskRun, utcnow


def _clear() -> None:
    with Session(engine) as session:
        session.exec(sa_delete(ScheduledTaskRun))
        session.exec(sa_delete(ScheduledTask))
        session.commit()


def _make_task(**fields) -> str:
    create_db_and_tables()
    fields.setdefault("name", "task")
    fields.setdefault("command", "echo hi")
    fields.setdefault("schedule", "* * * * *")
    with Session(engine) as session:
        task = ScheduledTask(**fields)
        session.add(task)
        session.commit()
        session.refresh(task)
        return task.id


def _wait_for_run(task_id: str) -> ScheduledTaskRun:
    for _ in range(100):
        with Session(engine) as session:
            run = session.exec(
                select(ScheduledTaskRun)
                .where(col(ScheduledTaskRun.scheduled_task_id) == task_id)
                .order_by(col(ScheduledTaskRun.started_at).desc())
            ).first()
        if run is not None and run.status != ScheduledRunStatus.running:
            return run
        time.sleep(0.05)
    raise AssertionError("run did not finish")


def test_schedule_crud_and_run_now():
    create_db_and_tables()
    _clear()
    with TestClient(app) as client:
        created = client.post("/api/schedules", json={"name": "hello", "command": "echo hi", "schedule": "*/5 * * * *"})
        assert created.status_code == 201
        task = created.json()
        assert task["next_run_at"] is not None
        assert task["timezone"] == str(schedules.SERVER_TIMEZONE)
        assert task["last_status"] is None

        # A schedule with the wrong field count, and blank name/command, are rejected.
        assert (
            client.post("/api/schedules", json={"name": "x", "command": "echo", "schedule": "nope"}).status_code == 400
        )
        assert (
            client.post("/api/schedules", json={"name": " ", "command": "echo", "schedule": "* * * * *"}).status_code
            == 400
        )
        assert (
            client.post("/api/schedules", json={"name": "x", "command": " ", "schedule": "* * * * *"}).status_code
            == 400
        )

        # Pausing clears the next run; enabling it again computes one.
        paused = client.patch(f"/api/schedules/{task['id']}", json={"enabled": False, "name": "renamed"}).json()
        assert paused["enabled"] is False
        assert paused["next_run_at"] is None
        assert paused["name"] == "renamed"
        assert client.patch(f"/api/schedules/{task['id']}", json={"enabled": True}).json()["next_run_at"] is not None
        assert client.patch(f"/api/schedules/{task['id']}", json={"schedule": "bad"}).status_code == 400

        # Run now: a run row is created and settles on its own.
        started = client.post(f"/api/schedules/{task['id']}/run")
        assert started.status_code == 201
        run_id = started.json()["id"]
        once = client.get(f"/api/schedules/runs/{run_id}").json()
        assert once["id"] == run_id

        run = _wait_for_run(task["id"])
        assert run.status == ScheduledRunStatus.succeeded
        assert run.exit_code == 0
        assert "hi" in run.output

        runs = client.get(f"/api/schedules/{task['id']}/runs").json()
        assert runs and runs[0]["id"] == run_id
        executions = client.get("/api/schedules/runs").json()
        assert executions and executions[0]["id"] == run_id
        assert executions[0]["task_name"] == "renamed"
        assert executions[0]["task_command"] == "echo hi"
        assert client.get("/api/schedules").json()[0]["last_status"] == "succeeded"

        for path in ("/api/schedules/nope", "/api/schedules/runs/nope"):
            assert client.get(path).status_code == 404
        assert client.patch("/api/schedules/nope", json={"name": "x"}).status_code == 404
        assert client.post("/api/schedules/nope/run").status_code == 404
        assert client.get("/api/schedules/nope/runs").status_code == 404
        assert client.delete("/api/schedules/nope").status_code == 404

        assert client.delete(f"/api/schedules/{task['id']}").status_code == 204
        assert client.get("/api/schedules").json() == []
    _clear()


def test_timezone_sets_when_the_schedule_fires():
    create_db_and_tables()
    _clear()
    with TestClient(app) as client:
        created = client.post(
            "/api/schedules",
            json={"name": "tokyo", "command": "echo hi", "schedule": "0 9 * * *", "timezone": "Asia/Tokyo"},
        )
        assert created.status_code == 201
        task = created.json()
        assert task["timezone"] == "Asia/Tokyo"
        # 09:00 in Tokyo is 00:00 UTC.
        assert task["next_run_at"].endswith("T00:00:00Z")

        preview = client.get(
            "/api/schedules/preview",
            params={"schedule": "0 9 * * *", "timezone": "Asia/Tokyo", "count": 3},
        )
        assert preview.status_code == 200
        assert preview.json()["timezone"] == "Asia/Tokyo"
        assert all(run.endswith("T00:00:00Z") for run in preview.json()["next_runs"])

        # An unknown zone is rejected on create and preview.
        unknown = {"name": "x", "command": "echo", "schedule": "* * * * *", "timezone": "Mars/Base"}
        assert client.post("/api/schedules", json=unknown).status_code == 400
        bad = client.get("/api/schedules/preview", params={"schedule": "* * * * *", "timezone": "Mars/Base"})
        assert bad.status_code == 400

        # Changing the zone recomputes the next occurrence.
        updated = client.patch(f"/api/schedules/{task['id']}", json={"timezone": "Europe/Paris"}).json()
        assert updated["timezone"] == "Europe/Paris"
        local = datetime.fromisoformat(updated["next_run_at"]).astimezone(ZoneInfo("Europe/Paris"))
        assert (local.hour, local.minute) == (9, 0)
    _clear()


def test_preview_returns_next_runs_and_rejects_bad_expressions():
    with TestClient(app) as client:
        ok = client.get("/api/schedules/preview", params={"schedule": "0 9 * * *", "count": 3})
        assert ok.status_code == 200
        assert len(ok.json()["next_runs"]) == 3
        assert ok.json()["timezone"] == str(schedules.SERVER_TIMEZONE)
        assert client.get("/api/schedules/preview", params={"schedule": "nope"}).status_code == 400


def test_next_run_keeps_the_wall_clock_across_dst(monkeypatch):
    # 09:00 stays 09:00 in the named zone even when the offset changes. The day
    # before the spring-forward, Paris is UTC+1; the run itself is UTC+2.
    monkeypatch.setattr(schedules, "SERVER_TIMEZONE", ZoneInfo("Europe/Paris"))
    base = datetime(2026, 3, 28, 9, 0, tzinfo=UTC)  # 10:00 in Paris
    assert schedules.compute_next_run("0 9 * * *", base=base) == datetime(2026, 3, 29, 7, 0, tzinfo=UTC)


def test_failed_command_and_bad_cwd_are_recorded():
    _clear()
    failing = _make_task(name="fails", command="exit 3")
    bad_cwd = _make_task(name="bad cwd", command="echo hi", cwd="/no/such/directory/here")

    with TestClient(app) as client:
        client.post(f"/api/schedules/{failing}/run")
        client.post(f"/api/schedules/{bad_cwd}/run")

    failed = _wait_for_run(failing)
    assert failed.status == ScheduledRunStatus.failed
    assert failed.exit_code == 3

    no_cwd = _wait_for_run(bad_cwd)
    assert no_cwd.status == ScheduledRunStatus.failed
    assert no_cwd.exit_code is None
    assert "does not exist" in no_cwd.output
    _clear()


@pytest.mark.asyncio
async def test_scheduler_runs_due_tasks_once():
    _clear()
    due = _make_task(name="due", command="echo due")
    paused = _make_task(name="paused", command="echo nope", enabled=False)
    future = _make_task(name="future", command="echo later")
    with Session(engine) as session:
        due_task = session.get(ScheduledTask, due)
        assert due_task is not None
        due_task.next_run_at = utcnow() - timedelta(minutes=1)
        paused_task = session.get(ScheduledTask, paused)
        assert paused_task is not None
        paused_task.next_run_at = utcnow() - timedelta(minutes=1)
        future_task = session.get(ScheduledTask, future)
        assert future_task is not None
        future_task.next_run_at = utcnow() + timedelta(days=1)
        session.add(due_task)
        session.add(paused_task)
        session.add(future_task)
        session.commit()

    assert await schedules.run_due_once() == 1
    # The due task's occurrence advanced into the future, so a second tick is a no-op.
    with Session(engine) as session:
        refreshed = session.get(ScheduledTask, due)
        assert refreshed is not None
        assert refreshed.next_run_at is not None
        assert refreshed.next_run_at > utcnow()
    for _ in range(100):
        with Session(engine) as session:
            run = session.exec(select(ScheduledTaskRun)).all()
        if run and all(row.status != ScheduledRunStatus.running for row in run):
            break
        await asyncio.sleep(0.05)
    assert [row.status for row in run] == [ScheduledRunStatus.succeeded]
    assert await schedules.run_due_once() == 0
    _clear()


def test_validate_schedule_and_next_run():
    assert schedules.validate_schedule("  0 9 * * * ") == "0 9 * * *"
    for bad in ("", "   ", "* * * *", "0 9 * * * *", "nope"):
        with pytest.raises(ValueError):
            schedules.validate_schedule(bad)
    nxt = schedules.compute_next_run("0 9 * * *")
    assert nxt.tzinfo is not None
    assert nxt > utcnow()
    # Cron means local wall-clock time, not UTC.
    local = nxt.astimezone()
    assert (local.hour, local.minute) == (9, 0)


def test_upcoming_runs_are_ordered_and_consistent():
    runs = schedules.upcoming_runs("0 9 * * *", count=5)
    assert len(runs) == 5
    assert runs == sorted(runs)
    assert all(run > utcnow() for run in runs)
    assert all(run.astimezone().hour == 9 for run in runs)
    # The stored next run leads the preview when it is still ahead.
    first = schedules.compute_next_run("0 9 * * *")
    assert schedules.upcoming_runs("0 9 * * *", first=first, count=2)[0] == first


def test_reconcile_marks_running_runs_failed():
    _clear()
    task_id = _make_task()
    with Session(engine) as session:
        run = ScheduledTaskRun(scheduled_task_id=task_id)
        session.add(run)
        session.commit()
        session.refresh(run)
        run_id = run.id
    assert schedules.reconcile_scheduled_runs() == 1
    with Session(engine) as session:
        row = session.get(ScheduledTaskRun, run_id)
        assert row is not None
        assert row.status == ScheduledRunStatus.failed
        assert "Interrupted" in row.output
    _clear()
