"""Task dependencies: the before/after edges between tasks.

Mounted under the same ``/api/tasks`` prefix as the task CRUD router; the
dependency read helper reuses the task read shape from ``tasks.py``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..crud import add_timeline, get_task_or_404
from ..db import get_session
from ..dependencies import dependencies, edge_exists, would_cycle
from ..events import bus
from ..models.base import DependencyRelation
from ..models.tasks import Task, TaskDependency
from ..schemas.tasks import DependencyCreate, TaskDependencies
from .tasks import _task_read

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _dependency_read(session: Session, task_id: str) -> TaskDependencies:
    before_ids, after_ids = dependencies(session, task_id)
    return TaskDependencies(
        task_id=task_id,
        before=[_task_read(session, task) for task in (session.get(Task, i) for i in before_ids) if task],
        after=[_task_read(session, task) for task in (session.get(Task, i) for i in after_ids) if task],
    )


@router.get("/{task_id}/dependencies", response_model=TaskDependencies)
def get_dependencies(task_id: str, session: Session = Depends(get_session)) -> TaskDependencies:
    """The tasks that come before and after this one in the dependency graph."""
    get_task_or_404(session, task_id)
    return _dependency_read(session, task_id)


@router.post("/{task_id}/dependencies", response_model=TaskDependencies, status_code=201)
async def add_dependency(
    task_id: str, payload: DependencyCreate, session: Session = Depends(get_session)
) -> TaskDependencies:
    """Link a related task before or after this one.

    ``relation="before"`` means the related task must be done first; ``"after"``
    means it follows this one. A link that would close a cycle is refused.
    """
    task = get_task_or_404(session, task_id)
    related = session.get(Task, payload.related_id)
    if related is None:
        raise HTTPException(status_code=404, detail="Related task not found")
    if related.id == task.id:
        raise HTTPException(status_code=400, detail="A task cannot be linked to itself")

    before, after = (related, task) if payload.relation == DependencyRelation.before else (task, related)
    if would_cycle(session, before.id, after.id):
        raise HTTPException(status_code=400, detail="That link would create a cycle")
    if not edge_exists(session, before.id, after.id):
        session.add(TaskDependency(before_id=before.id, after_id=after.id))
        session.commit()
        add_timeline(
            session,
            before.id,
            "dependency_added",
            f"Precedes: {after.title}",
            {"before_id": before.id, "after_id": after.id, "after_title": after.title},
        )
        add_timeline(
            session,
            after.id,
            "dependency_added",
            f"Follows: {before.title}",
            {"before_id": before.id, "after_id": after.id, "before_title": before.title},
        )
        await bus.publish(f"task:{task_id}", {"kind": "task", "action": "dependencies_changed"})
        await bus.publish(f"task:{related.id}", {"kind": "task", "action": "dependencies_changed"})
    return _dependency_read(session, task_id)


@router.delete("/{task_id}/dependencies/{related_id}", status_code=204)
async def remove_dependency(task_id: str, related_id: str, session: Session = Depends(get_session)) -> None:
    """Remove the before/after link between this task and a related one."""
    get_task_or_404(session, task_id)
    edge = session.exec(
        select(TaskDependency).where(
            ((TaskDependency.before_id == task_id) & (TaskDependency.after_id == related_id))
            | ((TaskDependency.before_id == related_id) & (TaskDependency.after_id == task_id))
        )
    ).first()
    if edge is None:
        raise HTTPException(status_code=404, detail="Dependency not found")

    before = session.get(Task, edge.before_id)
    after = session.get(Task, edge.after_id)
    session.delete(edge)
    session.commit()
    if before is not None and after is not None:
        add_timeline(
            session,
            before.id,
            "dependency_removed",
            f"No longer precedes: {after.title}",
            {"before_id": before.id, "after_id": after.id, "after_title": after.title},
        )
        add_timeline(
            session,
            after.id,
            "dependency_removed",
            f"No longer follows: {before.title}",
            {"before_id": before.id, "after_id": after.id, "before_title": before.title},
        )
    await bus.publish(f"task:{task_id}", {"kind": "task", "action": "dependencies_changed"})
    await bus.publish(f"task:{related_id}", {"kind": "task", "action": "dependencies_changed"})


__all__ = ["router"]
