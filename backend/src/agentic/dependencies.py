"""Links between tasks: the before/after graph, and symmetric related pairs.

An edge ``before_id -> after_id`` means the ``before`` task must be done before
the ``after`` task. The edges are kept acyclic: a link that would close a cycle
is refused, so the whole set always forms a DAG. A related pair is a separate,
symmetric link with no ordering, so it lives in its own table and never enters
the graph.
"""

from __future__ import annotations

from sqlmodel import Session, col, select

from .models.tasks import TaskDependency, TaskParent, TaskRelation


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


def parent_edge_exists(session: Session, parent_id: str, child_id: str) -> bool:
    """True when the exact parent -> child link is already stored."""
    return (
        session.exec(
            select(TaskParent).where(TaskParent.parent_id == parent_id, TaskParent.child_id == child_id)
        ).first()
        is not None
    )


def parent_link(session: Session, task_id: str, related_id: str) -> TaskParent | None:
    """The stored parent/child link between two tasks, from either side."""
    return session.exec(
        select(TaskParent).where(
            ((TaskParent.parent_id == task_id) & (TaskParent.child_id == related_id))
            | ((TaskParent.parent_id == related_id) & (TaskParent.child_id == task_id))
        )
    ).first()


def _reaches_child(session: Session, start_id: str, target_id: str) -> bool:
    """True when ``target_id`` is reachable from ``start_id`` following child edges."""
    seen = {start_id}
    frontier = [start_id]
    while frontier:
        current = frontier.pop()
        for edge in session.exec(select(TaskParent).where(TaskParent.parent_id == current)).all():
            if edge.child_id == target_id:
                return True
            if edge.child_id not in seen:
                seen.add(edge.child_id)
                frontier.append(edge.child_id)
    return False


def parent_would_cycle(session: Session, parent_id: str, child_id: str) -> bool:
    """True when adding ``parent_id -> child_id`` would close a cycle.

    A task cannot be its own parent, and a cycle appears when ``child_id`` is
    already an ancestor of ``parent_id`` (there is a path child -> ... -> parent).
    """
    if parent_id == child_id:
        return True
    return _reaches_child(session, child_id, parent_id)


def parents(session: Session, task_id: str) -> list[str]:
    """The tasks this one is a child of, oldest link first."""
    rows = session.exec(
        select(TaskParent).where(TaskParent.child_id == task_id).order_by(col(TaskParent.created_at))
    ).all()
    return [row.parent_id for row in rows]


def children(session: Session, task_id: str) -> list[str]:
    """The tasks that are children of this one, oldest link first."""
    rows = session.exec(
        select(TaskParent).where(TaskParent.parent_id == task_id).order_by(col(TaskParent.created_at))
    ).all()
    return [row.child_id for row in rows]


def related_pair(task_id: str, related_id: str) -> tuple[str, str]:
    """The pair as stored: the two ids ordered, so either side finds the row."""
    return (task_id, related_id) if task_id < related_id else (related_id, task_id)


def related_link(session: Session, task_id: str, related_id: str) -> TaskRelation | None:
    """The stored symmetric link between two tasks, if there is one."""
    first, second = related_pair(task_id, related_id)
    return session.exec(
        select(TaskRelation).where(TaskRelation.task_id == first, TaskRelation.related_id == second)
    ).first()


def related_ids(session: Session, task_id: str) -> list[str]:
    """The tasks linked to this one as related, oldest link first."""
    rows = session.exec(
        select(TaskRelation)
        .where((TaskRelation.task_id == task_id) | (TaskRelation.related_id == task_id))
        .order_by(col(TaskRelation.created_at))
    ).all()
    return [row.related_id if row.task_id == task_id else row.task_id for row in rows]


__all__ = [
    "all_edges",
    "children",
    "dependencies",
    "edge_exists",
    "parent_edge_exists",
    "parent_link",
    "parent_would_cycle",
    "parents",
    "related_ids",
    "related_link",
    "related_pair",
    "would_cycle",
]
