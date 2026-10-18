"""Pydantic request/response models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class InboxAction(BaseModel):
    """One thing the app can do to resolve a suggestion.

    ``kind`` says which existing endpoint performs it: ``set_task_status``
    patches the task, ``create_change`` records a change for an item, and
    ``remove_worktree`` prunes a worktree. The remaining fields carry what that
    call needs, so the client does not re-derive the state.
    """

    id: str
    kind: str
    label: str
    task_id: str
    status: str | None = None
    item_id: str | None = None
    worktree_id: str | None = None


class InboxSuggestion(BaseModel):
    """A thing worth doing, derived from the current state of a task."""

    id: str
    kind: str
    reason: str
    task_id: str
    task_title: str
    task_status: str
    actions: list[InboxAction] = []


class InboxReport(BaseModel):
    generated_at: datetime
    count: int = 0
    suggestions: list[InboxSuggestion] = []
