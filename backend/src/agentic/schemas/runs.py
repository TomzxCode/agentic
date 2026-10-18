"""Pydantic request/response models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from .base import ORMModel


class RunCreate(BaseModel):
    prompt: str
    harness_id: str | None = None
    worktree_id: str | None = None
    cwd: str | None = None


class SessionLink(BaseModel):
    """A way to open an agent session: a URL and/or a copyable command."""

    id: str  # openchamber | terminal | command
    label: str
    url: str | None = None
    command: str | None = None


class RunRead(ORMModel):
    id: str
    task_id: str
    harness_id: str | None = None
    cwd: str | None = None
    worktree_id: str | None = None
    prompt: str
    kind: str
    status: str
    session_id: str | None = None
    model: str | None = None
    stop_reason: str | None = None
    error: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    ended_at: datetime | None = None
    links: list[SessionLink] = []


class SessionCreate(BaseModel):
    """Attach an existing agent session to a task.

    ``harness_id`` defaults to the task's harness; ``cwd`` feeds the resume
    command and the terminal link.
    """

    session_id: str
    harness_id: str | None = None
    cwd: str | None = None
    label: str = ""


class SessionUpdate(BaseModel):
    harness_id: str | None = None
    cwd: str | None = None
    label: str | None = None


class SessionRead(ORMModel):
    id: str
    task_id: str
    harness_id: str | None = None
    session_id: str
    label: str
    cwd: str | None = None
    created_at: datetime
    links: list[SessionLink] = []


class AgentEventRead(ORMModel):
    id: int | None = None
    run_id: str
    seq: int
    type: str
    text: str
    # The payload the client renders a row from. An event arrives as `data` on
    # the SSE stream, so the stored endpoint emits the same key; only the
    # column is named `data_json`.
    data_json: dict[str, Any] = Field(default_factory=dict, serialization_alias="data")
    created_at: datetime


class ContextPreview(BaseModel):
    task_id: str
    summary: str
    next_steps: list[dict[str, Any]]
    context_updated_at: datetime | None = None
