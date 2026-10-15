"""Before/after links between tasks, and the graph they form.

An edge ``before_id -> after_id`` means the ``before`` task must be done before
the ``after`` task. The edges are kept acyclic: a link that would close a cycle
is refused, so the whole set always forms a DAG.
"""

from __future__ import annotations

from sqlmodel import Session, col, select

from .models import TaskDependency


def edge_exists(session: Session, before_id: str, after_id: str) -> bool:
    """True when the exact edge ``before_id -> after_id`` is already stored."""
    return (
        session.exec(
            select(TaskDependency).where(TaskDependency.before_id == before_id, TaskDependency.after_id == after_id)
        ).first()
        is not None
    )


def _reaches(session: Session, start_id: str, target_id: str) -> bool:
    """True when ``target_id`` is reachable from ``start_id`` following edges forward."""
    seen = {start_id}
    frontier = [start_id]
    while frontier:
        current = frontier.pop()
        for edge in session.exec(select(TaskDependency).where(TaskDependency.before_id == current)).all():
            if edge.after_id == target_id:
                return True
            if edge.after_id not in seen:
                seen.add(edge.after_id)
                frontier.append(edge.after_id)
    return False


def would_cycle(session: Session, before_id: str, after_id: str) -> bool:
    """True when adding ``before_id -> after_id`` would close a cycle.

    A task cannot come before itself, and a cycle appears when ``before_id`` is
    already reachable from ``after_id`` (there is a path after -> ... -> before).
    """
    if before_id == after_id:
        return True
    return _reaches(session, after_id, before_id)


def dependencies(session: Session, task_id: str) -> tuple[list[str], list[str]]:
    """Return ``(before_ids, after_ids)`` for a task, oldest link first."""
    edges = session.exec(
        select(TaskDependency)
        .where((TaskDependency.before_id == task_id) | (TaskDependency.after_id == task_id))
        .order_by(col(TaskDependency.created_at))
    ).all()
    before = [edge.before_id for edge in edges if edge.after_id == task_id]
    after = [edge.after_id for edge in edges if edge.before_id == task_id]
    return before, after


def all_edges(session: Session) -> list[TaskDependency]:
    """Every before/after edge, oldest first."""
    return list(session.exec(select(TaskDependency).order_by(col(TaskDependency.created_at))).all())


__all__ = ["all_edges", "dependencies", "edge_exists", "would_cycle"]
