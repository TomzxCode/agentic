"""SQLModel tables for execution graphs.

An execution graph is a named DAG of agent runs and input forms that the app
executes on demand or on a cron schedule. The graph holds the definition (its
nodes and edges) as JSON; one execution of it creates a task, and every run
node becomes an agent run attached to that task.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from .base import (
    GraphExecutionStatus,
    new_id,
    utcnow,
)


class ExecutionGraph(SQLModel, table=True):
    """A saved graph definition, started by its triggers or by hand.

    ``definition`` holds ``{"nodes": [...], "edges": [...]}`` in the shape
    ``agentic.graphs.normalize_definition`` produces; it is stored as the user
    arranged it in the editor, and validated before a run.

    The ``schedule``, ``timezone``, ``enabled``, and ``next_run_at`` columns are
    the pre-trigger design (one cron per graph). They stay for old databases but
    nothing reads them: ``db._migrate_graph_schedules_to_triggers`` moved each
    one into a :class:`GraphTrigger` row.
    """

    id: str = Field(default_factory=new_id, primary_key=True)
    name: str
    description: str = ""
    schedule: str | None = None
    timezone: str | None = None
    enabled: bool = True
    definition: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class GraphTrigger(SQLModel, table=True):
    """One way a graph starts: a schedule, a webhook, or a later type.

    ``config`` carries what the type needs: ``{"cron", "timezone"}`` for a
    schedule and ``{"secret"}`` for a webhook. Adding a type means giving it a
    config shape and a place that fires it, not a new column here.
    """

    id: str = Field(default_factory=new_id, primary_key=True)
    graph_id: str = Field(foreign_key="executiongraph.id", index=True)
    type: str = "schedule"
    config: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    enabled: bool = True
    # When the trigger fires next; only time-based types keep one. A schedule
    # advances it before the execution starts, so one occurrence fires once.
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class GraphExecution(SQLModel, table=True):
    """One run of an execution graph, with the task its agent runs attach to.

    ``state`` is the executor's working record, written on every node
    transition so the API can show progress without scraping transcripts: node
    statuses, each run node's output, and form answers. A paused execution
    waits for form answers in the API process, so a restart loses it; startup
    reconciliation marks such a run failed.
    """

    id: str = Field(default_factory=new_id, primary_key=True)
    graph_id: str = Field(foreign_key="executiongraph.id", index=True)
    task_id: str = Field(foreign_key="task.id", index=True)
    # manual | schedule | webhook: which trigger started it, and which of the
    # graph's trigger rows when it was one of them.
    trigger: str = "manual"
    trigger_id: str = ""
    status: GraphExecutionStatus = GraphExecutionStatus.running
    error: str = ""
    state: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    started_at: datetime = Field(default_factory=utcnow)
    ended_at: datetime | None = None
