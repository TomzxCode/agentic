"""Inbox: suggestions of things to do, derived from the current state.

The rules live in ``inbox.py`` (pure, database-free); this router loads the rows
they need, hands them over, and wraps the result in a report. Nothing is stored,
so a suggestion disappears as soon as the action it offers changes the state it
was derived from.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session, col, select

from ..db import get_session
from ..inbox import build_suggestions
from ..models import Association, Change, SourceItem, Task, Worktree, utcnow
from ..schemas import InboxReport

router = APIRouter(prefix="/api/inbox", tags=["inbox"])


@router.get("", response_model=InboxReport)
def get_inbox(session: Session = Depends(get_session)) -> InboxReport:
    """The current list of suggested actions, ordered by kind."""
    tasks = list(session.exec(select(Task).order_by(col(Task.updated_at).desc())).all())
    items_by_id = {item.id: item for item in session.exec(select(SourceItem)).all()}

    task_item_ids: dict[str, list[str]] = {}
    for assoc in session.exec(select(Association)).all():
        task_item_ids.setdefault(assoc.task_id, []).append(assoc.item_id)

    task_worktrees: dict[str, list[Worktree]] = {}
    for worktree in session.exec(select(Worktree)).all():
        task_worktrees.setdefault(worktree.task_id, []).append(worktree)

    task_changes: dict[str, list[Change]] = {}
    for change in session.exec(select(Change)).all():
        task_changes.setdefault(change.task_id, []).append(change)

    suggestions = build_suggestions(tasks, items_by_id, task_item_ids, task_worktrees, task_changes)
    return InboxReport(generated_at=utcnow(), count=len(suggestions), suggestions=suggestions)


__all__ = ["router"]
