"""SQLModel tables for changes."""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Field, SQLModel

from .base import (
    ChangeClass,
    ChangeStatus,
    InterventionKind,
    new_id,
    utcnow,
)


class Change(SQLModel, table=True):
    """One unit of factory output, instrumented for the autonomy and yield metrics.

    A change carries an id, a start (``opened_at``), an end (``accepted_at`` or
    ``closed_at``), and a human-intervened flag, which is everything the metric
    engine needs. It lives between the task that owns it and the interventions
    recorded against it.
    """

    id: str = Field(default_factory=new_id, primary_key=True)
    task_id: str = Field(foreign_key="task.id", index=True)
    title: str = ""
    change_class: ChangeClass = ChangeClass.feature
    status: ChangeStatus = Field(default=ChangeStatus.proposed, index=True)
    repository_id: str | None = Field(default=None, foreign_key="repository.id")
    worktree_id: str | None = Field(default=None, foreign_key="worktree.id")
    external_ref: str | None = None
    human_intervened: bool = False
    intervention_count: int = 0
    opened_at: datetime = Field(default_factory=utcnow)
    verified_at: datetime | None = None
    accepted_at: datetime | None = Field(default=None, index=True)
    closed_at: datetime | None = None
    notes: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class ChangeIntervention(SQLModel, table=True):
    """A recorded human touch on a change: a question, correction, fix, rerun, or approval."""

    id: str = Field(default_factory=new_id, primary_key=True)
    change_id: str = Field(foreign_key="change.id", index=True)
    kind: InterventionKind = InterventionKind.other
    note: str = ""
    created_at: datetime = Field(default_factory=utcnow)
