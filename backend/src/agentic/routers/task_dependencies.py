"""Task relations: the before/after edges, and the symmetric related pairs.

Mounted under the same ``/api/tasks`` prefix as the task CRUD router; the read
helper reuses the task read shape from ``tasks.py``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..checklists import apply_task_templates
from ..crud import add_timeline, get_or_404, get_task_or_404
from ..db import get_session
from ..dependencies import (
    dependencies,
    edge_exists,
    related_ids,
    related_link,
    related_pair,
    would_cycle,
)
from ..events import bus
from ..models.base import DependencyRelation
from ..models.tasks import Task, TaskDependency, TaskRelation
from ..schemas.tasks import DependencyCreate, TaskDependencies, TaskRead
from .task_service import _task_read

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _read_tasks(session: Session, task_ids: list[str]) -> list[TaskRead]:
    return [_task_read(session, task) for task in (session.get(Task, i) for i in task_ids) if task]


def _dependency_read(session: Session, task_id: str) -> TaskDependencies:
    before_ids, after_ids = dependencies(session, task_id)
    return TaskDependencies(
        task_id=task_id,
        before=_read_tasks(session, before_ids),
        after=_read_tasks(session, after_ids),
        related=_read_tasks(session, related_ids(session, task_id)),
    )


async def _publish_changed(task_id: str, related_id: str) -> None:
    await bus.publish(f"task:{task_id}", {"kind": "task", "action": "dependencies_changed"})
    await bus.publish(f"task:{related_id}", {"kind": "task", "action": "dependencies_changed"})


@router.get("/{task_id}/dependencies", response_model=TaskDependencies)
def get_dependencies(task_id: str, session: Session = Depends(get_session)) -> TaskDependencies:
    """The tasks linked to this one: before, after, and related."""
    get_task_or_404(session, task_id)
    return _dependency_read(session, task_id)


@router.post("/{task_id}/dependencies", response_model=TaskDependencies, status_code=201)
async def add_dependency(
    task_id: str, payload: DependencyCreate, session: Session = Depends(get_session)
) -> TaskDependencies:
    """Link a related task before or after this one, or as a related task.

    ``relation="before"`` means the related task must be done first; ``"after"``
    means it follows this one. Both are directed and a link that would close a
    cycle is refused. ``relation="related"`` stores a symmetric link, which
    reads the same from either task and is never part of the graph.
    """
    task = get_task_or_404(session, task_id)
    related = get_or_404(session, Task, payload.related_id, "Related task not found")
    if related.id == task.id:
        raise HTTPException(status_code=400, detail="A task cannot be linked to itself")

    if payload.relation == DependencyRelation.related:
        if related_link(session, task.id, related.id) is None:
            first, second = related_pair(task.id, related.id)
            session.add(TaskRelation(task_id=first, related_id=second))
            session.commit()
            add_timeline(
                session,
                task.id,
                "relation_added",
                f"Related: {related.title}",
                {"related_id": related.id, "related_title": related.title},
            )
            add_timeline(
                session,
                related.id,
                "relation_added",
                f"Related: {task.title}",
                {"related_id": task.id, "related_title": task.title},
            )
            apply_task_templates(session, task)
            apply_task_templates(session, related)
            await _publish_changed(task_id, related.id)
        return _dependency_read(session, task_id)

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
        apply_task_templates(session, before)
        apply_task_templates(session, after)
        await _publish_changed(task_id, related.id)
    return _dependency_read(session, task_id)


@router.delete("/{task_id}/dependencies/{related_id}", status_code=204)
async def remove_dependency(task_id: str, related_id: str, session: Session = Depends(get_session)) -> None:
    """Remove the link between this task and a related one, of either kind."""
    task = get_task_or_404(session, task_id)

    relation = related_link(session, task_id, related_id)
    if relation is not None:
        other = session.get(Task, related_id)
        session.delete(relation)
        session.commit()
        if other is not None:
            add_timeline(
                session,
                task.id,
                "relation_removed",
                f"No longer related: {other.title}",
                {"related_id": other.id, "related_title": other.title},
            )
            add_timeline(
                session,
                other.id,
                "relation_removed",
                f"No longer related: {task.title}",
                {"related_id": task.id, "related_title": task.title},
            )
        apply_task_templates(session, task)
        if other is not None:
            apply_task_templates(session, other)
        await _publish_changed(task_id, related_id)
        return

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
    if before is not None:
        apply_task_templates(session, before)
    if after is not None:
        apply_task_templates(session, after)
    await _publish_changed(task_id, related_id)


__all__ = ["router"]
