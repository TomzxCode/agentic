"""Execution graphs: CRUD, validation, and the runs of their executions.

The orchestration itself lives in ``agentic.graphs``; this router is the CRUD
surface plus "run now", the execution history, and the form answers that
unblock a paused execution.
"""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import delete as sa_delete
from sqlmodel import Session, col, select

from .. import graphs, triggers
from ..crud import get_or_404
from ..db import get_session
from ..models.base import RunStatus, utcnow
from ..models.graphs import ExecutionGraph, GraphExecution, GraphTrigger
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
    GraphTriggerInput,
    GraphTriggerRead,
)

router = APIRouter(prefix="/api/graphs", tags=["graphs"])


def _definition(payload: GraphDefinition) -> dict:
    return graphs.normalize_definition(payload.model_dump())


def _trigger_rows(session: Session, graph_id: str) -> list[GraphTrigger]:
    return list(
        session.exec(
            select(GraphTrigger)
            .where(col(GraphTrigger.graph_id) == graph_id)
            .order_by(col(GraphTrigger.created_at).asc())
        ).all()
    )


def _trigger_read(row: GraphTrigger) -> GraphTriggerRead:
    return GraphTriggerRead(
        id=row.id,
        type=row.type,
        config=row.config or {},
        enabled=row.enabled,
        next_run_at=row.next_run_at,
        last_run_at=row.last_run_at,
    )


def _read(session: Session, graph: ExecutionGraph) -> ExecutionGraphRead:
    rows = _trigger_rows(session, graph.id)
    upcoming = [row.next_run_at for row in rows if row.enabled and row.next_run_at is not None]
    return ExecutionGraphRead(
        id=graph.id,
        name=graph.name,
        description=graph.description,
        triggers=[_trigger_read(row) for row in rows],
        definition=graphs.normalize_definition(graph.definition),
        next_run_at=min(upcoming) if upcoming else None,
        last_run_at=graph.last_run_at,
        created_at=graph.created_at,
        updated_at=graph.updated_at,
        running_execution_id=graphs.active_execution_id(session, graph.id),
    )


def _normalized_triggers(submitted: list[GraphTriggerInput]) -> list[dict]:
    """The submitted triggers in stored shape, refusing any with a problem."""
    cleaned = [triggers.normalize(trigger.model_dump()) for trigger in submitted]
    problems = [problem for trigger in cleaned for problem in triggers.issues(trigger)]
    if problems:
        raise HTTPException(status_code=400, detail="; ".join(problems))
    return cleaned


def _apply_triggers(session: Session, graph: ExecutionGraph, submitted: list[dict]) -> None:
    """Make the graph's trigger rows match the submitted set.

    A trigger sent with an id of an existing row keeps that row (and its
    pending occurrence, unless its type, config, or enabled flag changed); a
    trigger without one, or with an id that is not this graph's, becomes a new
    row. Rows the payload leaves out are deleted.
    """
    existing = {row.id: row for row in _trigger_rows(session, graph.id)}
    keep: set[str] = set()
    for entry in submitted:
        row = existing.get(entry["id"]) if entry["id"] else None
        if row is None:
            row = GraphTrigger(graph_id=graph.id)
        changed = row.type != entry["type"] or row.config != entry["config"] or row.enabled != entry["enabled"]
        row.type = entry["type"]
        row.config = entry["config"]
        row.enabled = entry["enabled"]
        if changed or row.next_run_at is None:
            # Keep a pending occurrence when the trigger itself did not change,
            # so saving a renamed graph does not push its next run out.
            row.next_run_at = triggers.next_run(entry)
        row.updated_at = utcnow()
        session.add(row)
        keep.add(row.id)
    for trigger_id, row in existing.items():
        if trigger_id not in keep:
            session.delete(row)


def _validated_name(name: str | None) -> str:
    text = (name or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Name is required")
    return text


@router.get("", response_model=list[ExecutionGraphRead])
def list_graphs(session: Session = Depends(get_session)) -> list[ExecutionGraphRead]:
    """List graphs, the ones with the soonest next run first, manual only last."""
    rows = session.exec(select(ExecutionGraph).order_by(col(ExecutionGraph.created_at).desc())).all()
    reads = [_read(session, graph) for graph in rows]
    reads.sort(key=lambda read: (read.next_run_at is None, read.next_run_at.isoformat() if read.next_run_at else ""))
    return reads


@router.post("", response_model=ExecutionGraphRead, status_code=201)
def create_graph(payload: ExecutionGraphCreate, session: Session = Depends(get_session)) -> ExecutionGraphRead:
    """Create a graph from its settings, triggers, and whatever definition it carries.

    A new graph usually starts empty and is built in the editor, so the
    definition is only normalized here, never rejected; running it is where a
    broken definition fails with reasons.
    """
    graph = ExecutionGraph(
        name=_validated_name(payload.name),
        description=(payload.description or "").strip(),
        definition=_definition(payload.definition),
    )
    submitted = _normalized_triggers(payload.triggers)
    session.add(graph)
    session.flush()
    _apply_triggers(session, graph, submitted)
    session.commit()
    session.refresh(graph)
    return _read(session, graph)


@router.post("/validate", response_model=GraphIssuesRead)
def validate_graph(payload: ExecutionGraphCreate) -> GraphIssuesRead:
    """Check a definition and its triggers without saving either."""
    definition = _definition(payload.definition)
    issues = graphs.validate_definition(definition)
    for trigger in payload.triggers:
        issues.extend(triggers.issues(triggers.normalize(trigger.model_dump())))
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
    return [_execution_summary(execution, graph.name) for execution, graph in rows]


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
    return _execution_summary(execution, graph.name if graph else "")


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
    if payload.name is not None:
        graph.name = payload.name.strip() or graph.name
    if payload.description is not None:
        graph.description = payload.description.strip()
    if payload.definition is not None:
        # Stored as given (normalized); the editor flags problems live, and a
        # run refuses to start while anything is wrong.
        graph.definition = _definition(payload.definition)
    if payload.triggers is not None:
        # Omitted leaves the triggers alone (the editor saves only definitions);
        # a list replaces the whole set.
        _apply_triggers(session, graph, _normalized_triggers(payload.triggers))
    graph.updated_at = utcnow()
    session.add(graph)
    session.commit()
    session.refresh(graph)
    return _read(session, graph)


@router.delete("/{graph_id}", status_code=204)
def delete_graph(graph_id: str, session: Session = Depends(get_session)) -> None:
    get_or_404(session, ExecutionGraph, graph_id, "Graph not found")
    # Past runs keep living on their tasks; only the graph's own rows go.
    session.exec(sa_delete(GraphTrigger).where(col(GraphTrigger.graph_id) == graph_id))
    session.exec(sa_delete(GraphExecution).where(col(GraphExecution.graph_id) == graph_id))
    session.exec(sa_delete(ExecutionGraph).where(col(ExecutionGraph.id) == graph_id))
    session.commit()


def _execution_summary(execution: GraphExecution, graph_name: str) -> GraphExecutionSummaryRead:
    return GraphExecutionSummaryRead(
        id=execution.id,
        graph_id=execution.graph_id,
        graph_name=graph_name,
        task_id=execution.task_id,
        trigger=execution.trigger,
        status=execution.status.value,
        error=execution.error,
        started_at=execution.started_at,
        ended_at=execution.ended_at,
    )


async def _start_and_summarize(
    session: Session, graph: ExecutionGraph, *, trigger: str, trigger_id: str = ""
) -> GraphExecutionSummaryRead:
    """Start the graph and return its execution row, refusing like the run route."""
    if graphs.active_execution_id(session, graph.id):
        raise HTTPException(status_code=409, detail=f"'{graph.name}' already has a running execution")
    try:
        execution_id = await graphs.start_execution(session, graph, trigger=trigger, trigger_id=trigger_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    execution = session.get(GraphExecution, execution_id)
    if execution is None:  # pragma: no cover - the row was just created
        raise HTTPException(status_code=500, detail="Execution was not recorded")
    return _execution_summary(execution, graph.name)


@router.post("/{graph_id}/run", response_model=GraphExecutionSummaryRead, status_code=201)
async def run_graph(graph_id: str, session: Session = Depends(get_session)) -> GraphExecutionSummaryRead:
    """Start an execution immediately, in the background, and return its row."""
    graph = get_or_404(session, ExecutionGraph, graph_id, "Graph not found")
    return await _start_and_summarize(session, graph, trigger="manual")


@router.post("/{graph_id}/triggers/{trigger_id}/fire", response_model=GraphExecutionSummaryRead, status_code=201)
async def fire_webhook(
    graph_id: str,
    trigger_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> GraphExecutionSummaryRead:
    """Start the graph from a webhook trigger, for callers outside the app.

    The trigger's secret, when it has one, must arrive in the
    ``X-Trigger-Secret`` header, so a leaked URL alone does not start the graph.
    """
    graph = get_or_404(session, ExecutionGraph, graph_id, "Graph not found")
    trigger = session.get(GraphTrigger, trigger_id)
    if trigger is None or trigger.graph_id != graph_id:
        raise HTTPException(status_code=404, detail="Trigger not found")
    if trigger.type != triggers.WEBHOOK:
        raise HTTPException(status_code=400, detail="This trigger is not a webhook")
    if not trigger.enabled:
        raise HTTPException(status_code=403, detail="The trigger is disabled")
    secret = str((trigger.config or {}).get("secret") or "")
    if secret and not hmac.compare_digest(secret, request.headers.get("X-Trigger-Secret", "")):
        raise HTTPException(status_code=403, detail="The trigger secret does not match")
    summary = await _start_and_summarize(session, graph, trigger=trigger.type, trigger_id=trigger.id)
    trigger.last_run_at = utcnow()
    session.add(trigger)
    session.commit()
    return summary


__all__ = ["router"]
