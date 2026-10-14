"""Dependency graph: every task and the before/after edges between them.

The view that consumes this draws the DAG the before/after links form, so a
task's prerequisites and follow-ups are visible together.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session, col, select

from ..db import get_session
from ..dependencies import all_edges
from ..models import Task, TaskStatus
from ..schemas import DependencyGraph, GraphEdge, GraphNode

router = APIRouter(prefix="/api/graph", tags=["graph"])

# Tasks whose work is finished are hidden unless asked for, like the Gantt view.
CLOSED_STATUSES = (TaskStatus.done, TaskStatus.archived)


@router.get("", response_model=DependencyGraph)
def get_graph(include_done: bool = False, session: Session = Depends(get_session)) -> DependencyGraph:
    """Return the tasks as nodes (oldest first) and the edges between them."""
    tasks = list(session.exec(select(Task).order_by(col(Task.created_at))).all())
    if not include_done:
        tasks = [task for task in tasks if task.status not in CLOSED_STATUSES]

    ids = {task.id for task in tasks}
    # An edge to a task that is filtered out would dangle, so drop it too.
    edges = [edge for edge in all_edges(session) if edge.before_id in ids and edge.after_id in ids]

    return DependencyGraph(
        nodes=[GraphNode(id=task.id, title=task.title, status=task.status, priority=task.priority) for task in tasks],
        edges=[GraphEdge(before_id=edge.before_id, after_id=edge.after_id) for edge in edges],
    )


__all__ = ["router"]
