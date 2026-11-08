"""Task relations: before/after edges, related pairs, and the task hierarchy.

Mounted under the same ``/api/tasks`` prefix as the task CRUD router; the read
helper reuses the task read shape from ``tasks.py``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from ..checklists import apply_task_templates
from ..crud import add_timeline, get_or_404, get_task_or_404
from ..db import get_session
from ..dependencies import (
    children,
    dependencies,
    edge_exists,
    parent_edge_exists,
    parent_link,
    parent_would_cycle,
    parents,
    related_ids,
    related_link,
    related_pair,
    would_cycle,
)
from ..events import bus
from ..models.base import DependencyRelation
from ..models.tasks import Task, TaskDependency, TaskParent, TaskRelation
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
        parents=_read_tasks(session, parents(session, task_id)),
        children=_read_tasks(session, children(session, task_id)),
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
    """Link a related task before or after this one, as related, or as family.

    ``relation="before"`` means the related task must be done first; ``"after"``
    means it follows this one. Both are directed and a link that would close a
    cycle is refused. ``relation="related"`` stores a symmetric link, which
    reads the same from either task and is never part of the graph.
    ``relation="parent"`` makes the related task a parent of this one, and
    ``relation="child"`` makes it a child; those links form a separate acyclic
    hierarchy.
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

    if payload.relation in (DependencyRelation.parent, DependencyRelation.child):
        parent, child = (related, task) if payload.relation == DependencyRelation.parent else (task, related)
        if parent_would_cycle(session, parent.id, child.id):
            raise HTTPException(status_code=400, detail="That link would create a cycle")
        if not parent_edge_exists(session, parent.id, child.id):
            session.add(TaskParent(parent_id=parent.id, child_id=child.id))
            session.commit()
            add_timeline(
                session,
                parent.id,
                "parent_added",
                f"Child task added: {child.title}",
                {"parent_id": parent.id, "child_id": child.id, "child_title": child.title},
            )
            add_timeline(
                session,
                child.id,
                "parent_added",
                f"Parent task added: {parent.title}",
                {"parent_id": parent.id, "parent_title": parent.title, "child_id": child.id},
            )
            apply_task_templates(session, parent)
            apply_task_templates(session, child)
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
async def remove_dependency(
    task_id: str,
    related_id: str,
    relation: DependencyRelation | None = Query(default=None),
    session: Session = Depends(get_session),
) -> None:
    """Remove the link between this task and a related one.

    Without ``relation`` the first link found is removed (related, then parent,
    then before/after). Pass ``relation`` to remove one kind when the pair
    carries more than one.
    """
    task = get_task_or_404(session, task_id)

    if relation in (None, DependencyRelation.related):
        link = related_link(session, task_id, related_id)
        if link is not None:
            other = session.get(Task, related_id)
            session.delete(link)
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
        if relation == DependencyRelation.related:
            raise HTTPException(status_code=404, detail="Related link not found")

    if relation in (None, DependencyRelation.parent, DependencyRelation.child):
        link = parent_link(session, task_id, related_id)
        if link is not None:
            parent = session.get(Task, link.parent_id)
            child = session.get(Task, link.child_id)
            session.delete(link)
            session.commit()
            if parent is not None and child is not None:
                add_timeline(
                    session,
                    parent.id,
                    "parent_removed",
                    f"No longer a child: {child.title}",
                    {"parent_id": parent.id, "child_id": child.id, "child_title": child.title},
                )
                add_timeline(
                    session,
                    child.id,
                    "parent_removed",
                    f"No longer a parent: {parent.title}",
                    {"parent_id": parent.id, "parent_title": parent.title, "child_id": child.id},
                )
            if parent is not None:
                apply_task_templates(session, parent)
            if child is not None:
                apply_task_templates(session, child)
            await _publish_changed(task_id, related_id)
            return
        if relation in (DependencyRelation.parent, DependencyRelation.child):
            raise HTTPException(status_code=404, detail="Parent link not found")

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
