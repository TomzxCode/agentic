"""Pydantic request/response models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from .base import ORMModel


class ChangeCreate(BaseModel):
    task_id: str
    title: str = ""
    change_class: str = "feature"
    # The state the change opens in. Only the pre-landing and landed states are
    # accepted at creation; a change cannot be born rejected or reverted.
    status: str = "proposed"
    repository_id: str | None = None
    worktree_id: str | None = None
    external_ref: str | None = None
    notes: str = ""
    human_intervened: bool = False
    opened_at: datetime | None = None
    # The moment a change opens already accepted (e.g. an imported merged PR);
    # defaults to opened_at, then now.
    accepted_at: datetime | None = None


class ChangeUpdate(BaseModel):
    title: str | None = None
    change_class: str | None = None
    repository_id: str | None = None
    worktree_id: str | None = None
    external_ref: str | None = None
    notes: str | None = None


class ChangeStatusUpdate(BaseModel):
    status: str


class InterventionCreate(BaseModel):
    kind: str = "other"
    note: str = ""


class InterventionRead(ORMModel):
    id: str
    change_id: str
    kind: str
    note: str
    created_at: datetime


class ChangeRead(ORMModel):
    id: str
    task_id: str
    title: str
    change_class: str
    status: str
    repository_id: str | None = None
    worktree_id: str | None = None
    external_ref: str | None = None
    human_intervened: bool
    intervention_count: int
    opened_at: datetime
    verified_at: datetime | None = None
    accepted_at: datetime | None = None
    closed_at: datetime | None = None
    notes: str
    created_at: datetime
    updated_at: datetime


class ChangeDetail(ChangeRead):
    interventions: list[InterventionRead] = []
