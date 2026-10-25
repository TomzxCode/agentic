"""SQLModel tables for agents."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from .base import (
    RunStatus,
    new_id,
    utcnow,
)


class Harness(SQLModel, table=True):
    """A coding-agent harness reachable over ACP (opencode, pi, ...)."""

    id: str = Field(default_factory=new_id, primary_key=True)
    name: str
    description: str = ""
    command: str
    args: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    env: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON))
    model: str | None = None
    # Where the harness's own default model can be read from its config file,
    # written "<json file>#<template>". Read only, for display: a run that
    # selects no model gets whatever the harness resolves on its own, which this
    # reports without spawning the harness. Empty means no known source.
    default_model_source: str | None = None
    # Template for resuming a session in a terminal, e.g.
    # "opencode --session {session}". Placeholders: {session} {cwd} {harness}.
    resume_command: str | None = None
    is_default: bool = False
    created_at: datetime = Field(default_factory=utcnow)


class AgentRun(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    task_id: str = Field(foreign_key="task.id", index=True)
    harness_id: str | None = Field(default=None, foreign_key="harness.id")
    cwd: str | None = None
    worktree_id: str | None = Field(default=None, foreign_key="worktree.id")
    prompt: str = ""
    kind: str = "chat"  # chat | refresh_context
    status: RunStatus = RunStatus.queued
    session_id: str | None = None  # ACP session id
    # The model the run's session answers with, read from the ACP session's
    # ``model`` config option. Empty when the harness exposes none, so the
    # transcript says nothing rather than naming the harness's own default.
    model: str | None = None
    # The harness's own label for that model, read from the same session's model
    # list, so the UI shows "GLM 5.3" rather than the id the run selects with.
    # Empty when the harness does not name it.
    model_name: str | None = None
    # The model this run asked for, chosen in the task view; it takes precedence
    # over the harness's own configured model for this run only. Empty means the
    # harness decides.
    requested_model: str | None = None
    # Set when the run belongs to an execution graph. Plain ids, not foreign
    # keys: deleting a graph keeps its past runs (they belong to the execution's
    # task), so nothing may block on these references.
    graph_execution_id: str | None = Field(default=None, index=True)
    graph_node_id: str | None = None
    stop_reason: str | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    started_at: datetime | None = None
    ended_at: datetime | None = None


class AgentSession(SQLModel, table=True):
    """An agent session recorded against a task.

    A run stores the session it produced on its own row; this entity records a
    session attached by hand, for example one started in OpenChamber, so a task
    carries every session it was worked in plus the ways to reopen them.
    """

    id: str = Field(default_factory=new_id, primary_key=True)
    task_id: str = Field(foreign_key="task.id", index=True)
    harness_id: str | None = Field(default=None, foreign_key="harness.id")
    session_id: str  # the ACP (or agent) session id
    label: str = ""
    cwd: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


class AgentEvent(SQLModel, table=True):
    """A single normalized event in an agent run's transcript."""

    id: int | None = Field(default=None, primary_key=True)
    run_id: str = Field(foreign_key="agentrun.id", index=True)
    seq: int = 0
    type: str = "info"  # message | thought | tool_call | tool_update | plan | usage | model | status | error
    text: str = ""
    data_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)
