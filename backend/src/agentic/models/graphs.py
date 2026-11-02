"""SQLModel tables for execution graphs.

An execution graph is a named DAG of agent runs, commands, scripts, forms, and
trigger nodes (a webhook event or a schedule) that the app executes on demand or
when a trigger node fires. The graph holds the definition (its nodes and edges)
as JSON; one execution of it creates a task, and every agent run node becomes an
agent run attached to that task.
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
    """A saved graph definition, started by its trigger nodes or by hand.

    ``definition`` holds ``{"nodes": [...], "edges": [...]}`` in the shape
    ``agentic.graphs.normalize_definition`` produces; a schedule trigger is a
    node in it, so the cron lives with the rest of the graph rather than in a
    separate setting. ``schedule_state`` is the derived bookkeeping the
    scheduler keeps per schedule trigger node: its next and last occurrence.

    The ``schedule``, ``timezone``, ``enabled``, and ``next_run_at`` columns are
    the pre-trigger design (one cron per graph). They stay for old databases but
    nothing reads them; the migrations moved a schedule into a node.
    """

    id: str = Field(default_factory=new_id, primary_key=True)
    name: str
    description: str = ""
    schedule: str | None = None
    timezone: str | None = None
    enabled: bool = True
    definition: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    # {node_id: {nextRunAt, lastRunAt, cron, timezone}}, maintained from the
    # definition's schedule trigger nodes; never edited by the user.
    schedule_state: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
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
    # manual, schedule, or event:<type>: what started it, and the trigger
    # node's id when a node did.
    trigger: str = "manual"
    trigger_id: str = ""
    status: GraphExecutionStatus = GraphExecutionStatus.running
    error: str = ""
    state: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    started_at: datetime = Field(default_factory=utcnow)
    ended_at: datetime | None = None
