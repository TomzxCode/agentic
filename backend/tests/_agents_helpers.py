"""Shared helpers for the split ACP-layer tests."""

from sqlalchemy import delete as sa_delete
from sqlmodel import Session, col, select

from agentic.agents.harnesses import seed_harnesses
from agentic.db import create_db_and_tables, engine
from agentic.models.agents import AgentEvent, AgentRun
from agentic.models.tasks import Task, TimelineEvent


def _create_task_and_run() -> tuple[str, str]:
    create_db_and_tables()
    with Session(engine) as session:
        seed_harnesses(session)
        task = Task(title="run test")
        session.add(task)
        session.commit()
        session.refresh(task)
        run = AgentRun(task_id=task.id, kind="chat", prompt="p")
        session.add(run)
        session.commit()
        session.refresh(run)
        return task.id, run.id


def _delete_task(task_id: str) -> None:
    with Session(engine) as session:
        run_ids = [r.id for r in session.exec(select(AgentRun).where(AgentRun.task_id == task_id)).all()]
        if run_ids:
            session.exec(sa_delete(AgentEvent).where(col(AgentEvent.run_id).in_(run_ids)))
        session.exec(sa_delete(AgentRun).where(col(AgentRun.task_id) == task_id))
        session.exec(sa_delete(TimelineEvent).where(col(TimelineEvent.task_id) == task_id))
        session.exec(sa_delete(Task).where(col(Task.id) == task_id))
        session.commit()
