"""Pydantic request/response models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class InboxAction(BaseModel):
    """One thing the app can do to resolve a suggestion.

    ``kind`` says which existing endpoint performs it: ``set_task_status``
    patches the task, ``create_change`` records a change for an item,
    ``remove_worktree`` prunes a worktree, and ``open_url`` opens a link (a pull
    request awaiting a review). The remaining fields carry what that call or
    link needs, so the client does not re-derive the state.
    """

    id: str
    kind: str
    label: str
    task_id: str | None = None
    status: str | None = None
    item_id: str | None = None
    worktree_id: str | None = None
    url: str | None = None


class InboxSuggestion(BaseModel):
    """A thing worth doing, derived from a task or a pull request awaiting review.

    A suggestion about a task carries ``task_id`` and ``task_title``. One about
    a pull request past its review SLO carries ``repository``, ``number``,
    ``title``, and ``url`` instead, since that pull request may have no task.
    """

    id: str
    kind: str
    reason: str
    task_id: str | None = None
    task_title: str = ""
    task_status: str = ""
    repository: str | None = None
    number: int | None = None
    title: str | None = None
    url: str | None = None
    actions: list[InboxAction] = []


class InboxReport(BaseModel):
    generated_at: datetime
    count: int = 0
    suggestions: list[InboxSuggestion] = []
