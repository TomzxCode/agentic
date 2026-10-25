"""Execution graphs: CRUD, validation, and the runs of their executions.

The orchestration itself lives in ``agentic.graphs``; this router is the CRUD
surface plus "run now", the execution history, and the form answers that
unblock a paused execution.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete as sa_delete
from sqlmodel import Session, col, select

from .. import graphs, schedules
from ..crud import get_or_404
from ..db import get_session
from ..models.base import RunStatus, utcnow
from ..models.graphs import ExecutionGraph, GraphExecution
from ..schemas.graphs import (
    ExecutionGraphCreate,
    ExecutionGraphRead,
    ExecutionGraphUpdate,
    GraphDefinition,
    GraphExecutionRead,
    GraphExecutionSummaryRead,
    GraphFormRequestRead,
    GraphFormSubmit,
    GraphIssuesRead,
    GraphNodeStateRead,
)

router = APIRouter(prefix="/api/graphs", tags=["graphs"])


def _definition(payload: GraphDefinition) -> dict:
    return graphs.normalize_definition(payload.model_dump())


def _resolved_timezone(name: str | None) -> str:
    return str(schedules.resolve_timezone(name))


def _read(session: Session, graph: ExecutionGraph) -> ExecutionGraphRead:
    return ExecutionGraphRead(
        id=graph.id,
        name=graph.name,
        description=graph.description,
        schedule=graph.schedule,
        timezone=_resolved_timezone(graph.timezone),
        enabled=graph.enabled,
        definition=graphs.normalize_definition(graph.definition),
        next_run_at=graph.next_run_at,
        last_run_at=graph.last_run_at,
        created_at=graph.created_at,
        updated_at=graph.updated_at,
        running_execution_id=graphs.active_execution_id(session, graph.id),
    )


def _validate_fields(name: str, definition: dict, schedule: str | None) -> tuple[str, str | None]:
    name = (name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    issues = graphs.validate_definition(definition)
    if issues:
        raise HTTPException(status_code=400, detail="; ".join(issues))
    if schedule and not _cron(schedule):
        raise HTTPException(status_code=400, detail="The schedule is not a valid cron expression")
    return name, schedule


def _cron(expression: str) -> str | None:
    """The validated expression, or None when empty; raises 400 when invalid."""
    text = (expression or "").strip()
    if not text:
        return None
    try:
        return schedules.validate_schedule(text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _recompute_next_run(graph: ExecutionGraph) -> None:
    if not graph.enabled or not graph.schedule:
        graph.next_run_at = None
    else:
        from ..schedules import compute_next_run

        graph.next_run_at = compute_next_run(graph.schedule, timezone=graph.timezone)


@router.get("", response_model=list[ExecutionGraphRead])
def list_graphs(session: Session = Depends(get_session)) -> list[ExecutionGraphRead]:
    """List graphs, enabled ones first, soonest next run first."""
    rows = session.exec(
        select(ExecutionGraph).order_by(
            col(ExecutionGraph.enabled).desc(),
            col(ExecutionGraph.next_run_at).asc(),
            col(ExecutionGraph.created_at).desc(),
        )
    ).all()
    return [_read(session, graph) for graph in rows]


@router.post("", response_model=ExecutionGraphRead, status_code=201)
def create_graph(payload: ExecutionGraphCreate, session: Session = Depends(get_session)) -> ExecutionGraphRead:
    definition = _definition(payload.definition)
    name, schedule = _validate_fields(payload.name, definition, payload.schedule)
    graph = ExecutionGraph(
        name=name,
        description=(payload.description or "").strip(),
        schedule=schedule,
        timezone=_timezone_or_none(payload.timezone),
        enabled=payload.enabled,
        definition=definition,
    )
    _recompute_next_run(graph)
    session.add(graph)
    session.commit()
    session.refresh(graph)
    return _read(session, graph)


@router.post("/validate", response_model=GraphIssuesRead)
def validate_graph(payload: ExecutionGraphCreate) -> GraphIssuesRead:
    """Check a definition (and its schedule) without saving it."""
    definition = _definition(payload.definition)
    issues = graphs.validate_definition(definition)
    if (payload.schedule or "").strip():
        try:
            schedules.validate_schedule(payload.schedule or "")
        except ValueError as exc:
            issues.append(str(exc))
    try:
        _resolved_timezone(payload.timezone)
    except ValueError as exc:
        issues.append(str(exc))
    return GraphIssuesRead(issues=issues)


@router.get("/executions", response_model=list[GraphExecutionSummaryRead])
def list_executions(
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_session),
) -> list[GraphExecutionSummaryRead]:
    """Every execution across all graphs, newest first."""
    rows = session.exec(
        select(GraphExecution, ExecutionGraph)
        .join(ExecutionGraph, col(GraphExecution.graph_id) == col(ExecutionGraph.id))
        .order_by(col(GraphExecution.started_at).desc())
        .limit(limit)
    ).all()
    return [
        GraphExecutionSummaryRead(
            id=execution.id,
            graph_id=execution.graph_id,
            graph_name=graph.name,
            task_id=execution.task_id,
            trigger=execution.trigger,
            status=execution.status.value,
            error=execution.error,
            started_at=execution.started_at,
            ended_at=execution.ended_at,
        )
        for execution, graph in rows
    ]


@router.get("/executions/{execution_id}", response_model=GraphExecutionRead)
def get_execution(execution_id: str, session: Session = Depends(get_session)) -> GraphExecutionRead:
    execution = get_or_404(session, GraphExecution, execution_id, "Execution not found")
    graph = get_or_404(session, ExecutionGraph, execution.graph_id, "Graph not found")
    return _execution_read(session, execution, graph)


def _execution_read(session: Session, execution: GraphExecution, graph: ExecutionGraph) -> GraphExecutionRead:
    """An execution's nodes with their live statuses, forms, and outputs."""
    from ..models.agents import AgentRun

    definition = graphs.normalize_definition(graph.definition)
    nodes_by_id = {node["id"]: node for node in definition["nodes"]}
    state = execution.state or {}
    run_ids = [node_state.get("runId") for node_state in (state.get("nodes") or {}).values() if node_state.get("runId")]
    runs: dict[str, AgentRun] = {}
    if run_ids:
        for run in session.exec(select(AgentRun).where(col(AgentRun.id).in_(run_ids))).all():
            runs[run.id] = run
    node_reads: list[GraphNodeStateRead] = []
    for node_id in state.get("order") or list(nodes_by_id):
        node = nodes_by_id.get(node_id)
        node_state = (state.get("nodes") or {}).get(node_id) or {}
        if node is None:
            continue
        run = runs.get(node_state.get("runId") or "")
        # The live run row is the truth about a run node's outcome; the state
        # is what the executor last recorded. Both vocabularies mean the same
        # thing: succeeded is done, a cancelled run skipped its node.
        status = node_state.get("status", graphs.NODE_PENDING)
        if run is not None:
            if run.status == RunStatus.succeeded:
                status = "done"
            elif run.status == RunStatus.failed:
                status = "failed"
            elif run.status == RunStatus.cancelled:
                status = "skipped"
            else:
                status = run.status.value
        node_reads.append(
            GraphNodeStateRead(
                node_id=node_id,
                kind=node["kind"],
                title=node.get("title") or node_id,
                status=status,
                run_id=node_state.get("runId"),
                error=node_state.get("error", ""),
                output=(state.get("outputs") or {}).get(node_id, ""),
                started_at=node_state.get("startedAt"),
                ended_at=node_state.get("endedAt"),
            )
        )
    pending_form = None
    pending = state.get("pendingForm")
    if pending and execution.status.value == "running":
        node = nodes_by_id.get(pending.get("nodeId") or "")
        if node is not None:
            from ..schemas.graphs import GraphFormField

            pending_form = GraphFormRequestRead(
                node_id=node["id"],
                title=node.get("title") or node["id"],
                requested_at=pending.get("requestedAt", ""),
                defaults=pending.get("defaults") or {},
                fields=[GraphFormField(**field) for field in node.get("fields") or []],
            )
    return GraphExecutionRead(
        id=execution.id,
        graph_id=graph.id,
        graph_name=graph.name,
        task_id=execution.task_id,
        trigger=execution.trigger,
        status=execution.status.value,
        error=execution.error,
        nodes=node_reads,
        pending_form=pending_form,
        started_at=execution.started_at,
        ended_at=execution.ended_at,
    )


@router.post("/executions/{execution_id}/cancel", response_model=GraphExecutionSummaryRead)
async def cancel_execution(execution_id: str, session: Session = Depends(get_session)) -> GraphExecutionSummaryRead:
    execution = get_or_404(session, GraphExecution, execution_id, "Execution not found")
    if not await graphs.cancel_execution(execution_id):
        raise HTTPException(status_code=409, detail="Execution is not running")
    session.refresh(execution)
    graph = session.get(ExecutionGraph, execution.graph_id)
    return GraphExecutionSummaryRead(
        id=execution.id,
        graph_id=execution.graph_id,
        graph_name=graph.name if graph else "",
        task_id=execution.task_id,
        trigger=execution.trigger,
        status=execution.status.value,
        error=execution.error,
        started_at=execution.started_at,
        ended_at=execution.ended_at,
    )


@router.post("/executions/{execution_id}/forms/{node_id}", response_model=GraphExecutionRead)
async def submit_form(
    execution_id: str, node_id: str, payload: GraphFormSubmit, session: Session = Depends(get_session)
) -> GraphExecutionRead:
    """Answer (or cancel) the form an execution is waiting on."""
    execution = get_or_404(session, GraphExecution, execution_id, "Execution not found")
    graph = get_or_404(session, ExecutionGraph, execution.graph_id, "Graph not found")
    if not await graphs.submit_form(execution_id, node_id, payload.values, cancel=payload.cancel):
        raise HTTPException(status_code=409, detail="The execution is not waiting on this form")
    session.refresh(execution)
    return _execution_read(session, execution, graph)


@router.get("/{graph_id}", response_model=ExecutionGraphRead)
def get_graph(graph_id: str, session: Session = Depends(get_session)) -> ExecutionGraphRead:
    return _read(session, get_or_404(session, ExecutionGraph, graph_id, "Graph not found"))


@router.patch("/{graph_id}", response_model=ExecutionGraphRead)
def update_graph(
    graph_id: str, payload: ExecutionGraphUpdate, session: Session = Depends(get_session)
) -> ExecutionGraphRead:
    graph = get_or_404(session, ExecutionGraph, graph_id, "Graph not found")
    data = payload.model_dump(exclude_unset=True)
    if data.get("name") is not None:
        graph.name = data["name"].strip() or graph.name
    if data.get("description") is not None:
        graph.description = data["description"].strip()
    if data.get("enabled") is not None:
        graph.enabled = data["enabled"]
    schedule_changed = False
    if "schedule" in data:
        graph.schedule = _cron(data["schedule"] or "")
        schedule_changed = True
    timezone_changed = "timezone" in data
    if timezone_changed:
        graph.timezone = _timezone_or_none(data["timezone"])
        schedule_changed = True
    if payload.definition is not None:
        definition = _definition(payload.definition)
        issues = graphs.validate_definition(definition)
        if issues:
            raise HTTPException(status_code=400, detail="; ".join(issues))
        graph.definition = definition
    # Recompute the next occurrence only when it is actually affected, so
    # renaming a graph does not push a pending run further out.
    if not graph.enabled:
        graph.next_run_at = None
    elif schedule_changed or graph.next_run_at is None:
        _recompute_next_run(graph)
    graph.updated_at = utcnow()
    session.add(graph)
    session.commit()
    session.refresh(graph)
    return _read(session, graph)


@router.delete("/{graph_id}", status_code=204)
def delete_graph(graph_id: str, session: Session = Depends(get_session)) -> None:
    get_or_404(session, ExecutionGraph, graph_id, "Graph not found")
    # Past runs keep living on their tasks; only the graph's own rows go.
    session.exec(sa_delete(GraphExecution).where(col(GraphExecution.graph_id) == graph_id))
    session.exec(sa_delete(ExecutionGraph).where(col(ExecutionGraph.id) == graph_id))
    session.commit()


@router.post("/{graph_id}/run", response_model=GraphExecutionSummaryRead, status_code=201)
async def run_graph(graph_id: str, session: Session = Depends(get_session)) -> GraphExecutionSummaryRead:
    """Start an execution immediately, in the background, and return its row."""
    graph = get_or_404(session, ExecutionGraph, graph_id, "Graph not found")
    if graphs.active_execution_id(session, graph_id):
        raise HTTPException(status_code=409, detail=f"'{graph.name}' already has a running execution")
    try:
        execution_id = await graphs.start_execution(session, graph, trigger="manual")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    execution = session.get(GraphExecution, execution_id)
    if execution is None:  # pragma: no cover - the row was just created
        raise HTTPException(status_code=500, detail="Execution was not recorded")
    return GraphExecutionSummaryRead(
        id=execution.id,
        graph_id=execution.graph_id,
        graph_name=graph.name,
        task_id=execution.task_id,
        trigger=execution.trigger,
        status=execution.status.value,
        error=execution.error,
        started_at=execution.started_at,
        ended_at=execution.ended_at,
    )


def _timezone_or_none(value: str | None) -> str | None:
    """Canonical zone name, or None to follow the server's timezone."""
    text = (value or "").strip()
    if not text:
        return None
    try:
        schedules.resolve_timezone(text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return text


__all__ = ["router"]
