"""Pydantic request/response models for execution graphs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from .base import ORMModel


class GraphNodePosition(BaseModel):
    x: float = 0
    y: float = 0


class GraphNodeInput(BaseModel):
    id: str
    name: str


class GraphFormField(BaseModel):
    id: str
    title: str
    type: str = "text"
    required: bool = False
    placeholder: str = ""
    defaultValue: str = ""
    options: list[str] = []
    min: float | None = None
    max: float | None = None
    step: float | None = None


class GraphNode(BaseModel):
    """One node of the definition, as the editor draws it."""

    id: str
    kind: str = "run"
    title: str = ""
    position: GraphNodePosition = GraphNodePosition()
    # Run nodes
    harnessId: str = ""
    model: str = ""
    cwd: str = ""
    promptTemplate: str = ""
    inputs: list[GraphNodeInput] = []
    # Cli nodes (the command line after `agentic`, with {{name}} placeholders)
    command: str = ""
    # Form nodes
    fields: list[GraphFormField] = []


class GraphEdge(BaseModel):
    id: str
    source: str
    # Empty on a run node's output; a form node's field id otherwise.
    sourceFieldId: str = ""
    target: str
    # Set when the target is a run node, empty when it is a form field default.
    targetInputId: str = ""
    targetFieldId: str = ""


class GraphDefinition(BaseModel):
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []


class ExecutionGraphCreate(BaseModel):
    name: str
    description: str = ""
    # A 5-field cron expression; omitted or empty means manual only.
    schedule: str | None = None
    timezone: str | None = None
    enabled: bool = True
    definition: GraphDefinition = GraphDefinition()


class ExecutionGraphUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    schedule: str | None = None
    timezone: str | None = None
    enabled: bool | None = None
    definition: GraphDefinition | None = None


class ExecutionGraphRead(ORMModel):
    id: str
    name: str
    description: str
    schedule: str | None = None
    # The zone the cron is evaluated in, resolved to the server's when unset.
    timezone: str
    enabled: bool
    definition: dict[str, Any]
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    # The running execution, so the list can show what is in flight.
    running_execution_id: str | None = None


class GraphIssuesRead(BaseModel):
    """The problems found in a definition, for the editor's validate action."""

    issues: list[str] = []


class GraphNodeStateRead(BaseModel):
    """One node's state in an execution, for the executions tab."""

    node_id: str
    kind: str
    title: str
    status: str
    run_id: str | None = None
    error: str = ""
    output: str = ""
    started_at: str | None = None
    ended_at: str | None = None


class GraphFormRequestRead(BaseModel):
    """The form an execution is waiting on, with its fields as declared."""

    node_id: str
    title: str
    requested_at: str = ""
    defaults: dict[str, str] = {}
    fields: list[GraphFormField] = []


class GraphExecutionRead(ORMModel):
    id: str
    graph_id: str
    graph_name: str
    task_id: str
    trigger: str
    status: str
    error: str = ""
    nodes: list[GraphNodeStateRead] = []
    pending_form: GraphFormRequestRead | None = None
    started_at: datetime
    ended_at: datetime | None = None


class GraphExecutionSummaryRead(ORMModel):
    """One row of the cross-graph execution history."""

    id: str
    graph_id: str
    graph_name: str
    task_id: str
    trigger: str
    status: str
    error: str = ""
    started_at: datetime
    ended_at: datetime | None = None


class GraphFormSubmit(BaseModel):
    values: dict[str, str] = {}
    cancel: bool = False
