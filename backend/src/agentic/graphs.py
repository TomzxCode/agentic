"""Execution graphs: DAGs of agent runs, CLI commands, and forms, fired on demand or cron.

A graph definition is ``{"nodes": [...], "edges": [...]}``. A run node holds a
prompt template whose ``{{name}}`` placeholders read named inputs; a cli node
holds an agentic CLI command line whose placeholders fill its arguments; an
edge feeds one upstream output (an agent run's final answer, a command's
stdout, or a form field value) into one downstream input. A form node pauses
the execution until someone answers it in the web UI, and its answers flow
downstream like run outputs.

The executor walks the DAG in the API process: it renders each ready run
node's prompt, enqueues an agent run on the SAQ queue, and polls the run's row
until a worker settles it. The runs themselves are durable; the walk is not,
so startup reconciliation marks an execution left ``running`` by a restart as
failed. Forms are answered through :func:`submit_form`, which resolves the
future the executor awaits.

The pure helpers (normalization, validation, template rendering, ordering) are
the graph's contract and are safe to call from anywhere; everything async here
owns the execution.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import re
import shlex
from typing import Any

import structlog
from sqlalchemy import or_
from sqlmodel import Session, col, select

from .config import settings
from .db import engine
from .models.agents import AgentEvent, AgentRun
from .models.base import GraphExecutionStatus, RunStatus, TaskStatus, utcnow
from .models.graphs import ExecutionGraph, GraphExecution
from .models.tasks import Task

log = structlog.get_logger(__name__)

# --- definition contract ---------------------------------------------------

NODE_KINDS = ("run", "form", "cli")
FIELD_TYPES = ("text", "textarea", "number", "date", "time", "select", "slider", "checkbox")
# Field types whose value is a number bounded by min/max/step.
NUMERIC_FIELD_TYPES = ("number", "slider")

# Nodes with named inputs and one output (the node kinds an edge can feed).
OUTPUT_NODE_KINDS = ("run", "cli")

MAX_NODES = 32
MAX_FIELDS = 20
MAX_SELECT_OPTIONS = 20

# Input names appear inside template placeholders, so they may not contain
# whitespace or any character that is part of the placeholder grammar.
INPUT_NAME_RE = re.compile(r'^[^\s.\[\]{}"()]+$')
# {{name}}, {{name[2]}}, and {{name.join(", ")}} are the whole language.
TEMPLATE_RE = re.compile(r'\{\{\s*([^\s.\[\]{}"()]+)\s*(?:\[\s*(\d+)\s*\]|\.\s*join\(\s*"([^"]*)"\s*\))?\s*\}\}')

# Node statuses, as stored in the execution state and shown by the API.
NODE_PENDING = "pending"
NODE_WAITING = "waiting"  # a form node waiting for an answer
NODE_RUNNING = "running"
NODE_DONE = "done"  # a run finished, or a form was answered
NODE_FAILED = "failed"  # a run failed, or a form was cancelled
NODE_SKIPPED = "skipped"  # an upstream failed, or the form was never needed

TERMINAL_NODE_STATES = {NODE_DONE, NODE_FAILED, NODE_SKIPPED}

# Keep at most this many characters of a run node's output, both in the state
# row and as a downstream input value.
MAX_OUTPUT = 20_000

# How often the executor polls a running run's row. A run lasts seconds to
# minutes, so this adds no perceptible delay and is cheap on SQLite.
POLL_SECONDS = 1.0


def normalize_definition(raw: Any) -> dict[str, Any]:
    """Coerce a stored or submitted definition into the known shape.

    Unknown keys, kinds, and field types are dropped, ids and positions are
    coerced, and caps are enforced by keeping the first entries. Semantic
    problems are validation's job, not ours.
    """
    if not isinstance(raw, dict):
        return {"nodes": [], "edges": []}
    nodes: list[dict[str, Any]] = []
    for node in raw.get("nodes") or []:
        if len(nodes) >= MAX_NODES:
            break
        if not isinstance(node, dict):
            continue
        kind = node.get("kind")
        if kind not in NODE_KINDS:
            continue
        clean: dict[str, Any] = {
            "id": str(node.get("id") or "").strip(),
            "kind": kind,
            "title": str(node.get("title") or "").strip(),
            "position": _position(node.get("position")),
        }
        if kind == "run":
            clean["harnessId"] = str(node.get("harnessId") or "").strip()
            clean["model"] = str(node.get("model") or "").strip()
            clean["cwd"] = str(node.get("cwd") or "").strip()
            clean["promptTemplate"] = str(node.get("promptTemplate") or "")
            clean["inputs"] = _inputs(node.get("inputs"))
        elif kind == "cli":
            clean["command"] = str(node.get("command") or "")
            clean["cwd"] = str(node.get("cwd") or "").strip()
            clean["inputs"] = _inputs(node.get("inputs"))
        else:
            clean["fields"] = _fields(node.get("fields"))
        nodes.append(clean)
    edges: list[dict[str, Any]] = []
    for edge in raw.get("edges") or []:
        if not isinstance(edge, dict):
            continue
        edges.append(
            {
                "id": str(edge.get("id") or "").strip(),
                "source": str(edge.get("source") or "").strip(),
                "sourceFieldId": str(edge.get("sourceFieldId") or "").strip(),
                "target": str(edge.get("target") or "").strip(),
                "targetInputId": str(edge.get("targetInputId") or "").strip(),
                "targetFieldId": str(edge.get("targetFieldId") or "").strip(),
            }
        )
    return {"nodes": nodes, "edges": edges}


def _position(raw: Any) -> dict[str, float]:
    if not isinstance(raw, dict):
        return {"x": 0.0, "y": 0.0}
    try:
        return {"x": float(raw.get("x") or 0.0), "y": float(raw.get("y") or 0.0)}
    except (TypeError, ValueError):
        return {"x": 0.0, "y": 0.0}


def _inputs(raw: Any) -> list[dict[str, str]]:
    inputs: list[dict[str, str]] = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        inputs.append({"id": str(item.get("id") or "").strip(), "name": name})
    return inputs


def _fields(raw: Any) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    for item in raw or []:
        if len(fields) >= MAX_FIELDS:
            break
        if not isinstance(item, dict):
            continue
        type_ = item.get("type")
        if type_ not in FIELD_TYPES:
            continue
        field: dict[str, Any] = {
            "id": str(item.get("id") or "").strip(),
            "title": str(item.get("title") or "").strip(),
            "type": type_,
            "required": bool(item.get("required")),
            "placeholder": str(item.get("placeholder") or ""),
            "defaultValue": str(item.get("defaultValue") or ""),
        }
        if type_ == "select":
            options = [str(option) for option in (item.get("options") or []) if str(option).strip()]
            field["options"] = options[:MAX_SELECT_OPTIONS]
        if type_ in NUMERIC_FIELD_TYPES:
            for key in ("min", "max", "step"):
                try:
                    field[key] = float(item.get(key)) if item.get(key) is not None else None
                except (TypeError, ValueError):
                    field[key] = None
        fields.append(field)
    return fields


# --- validation ------------------------------------------------------------
def validate_definition(definition: dict[str, Any]) -> list[str]:
    """Every problem that would stop a run or confuse the editor, in English."""
    issues: list[str] = []
    nodes = definition.get("nodes") or []
    edges = definition.get("edges") or []
    if not nodes:
        issues.append("The graph needs at least one node")
    if len(nodes) > MAX_NODES:
        issues.append(f"A graph holds at most {MAX_NODES} nodes")

    by_id: dict[str, dict[str, Any]] = {}
    for node in nodes:
        node_id = node.get("id") or ""
        if not node_id:
            issues.append("A node is missing its id")
            continue
        if node_id in by_id:
            issues.append(f"Duplicate node id '{node_id}'")
            continue
        by_id[node_id] = node
        title = node.get("title") or ""
        if not title:
            issues.append(f"Node '{node_id}' needs a title")
        if node.get("kind") == "form":
            issues.extend(_validate_form_node(node))
        else:
            issues.extend(_validate_output_node(node))

    titles = [node.get("title") for node in nodes if node.get("title")]
    for title in set(titles):
        if titles.count(title) > 1:
            issues.append(f"Two nodes are titled '{title}'")

    seen_edges: set[str] = set()
    for edge in edges:
        issues.extend(_validate_edge(edge, by_id, seen_edges))

    # A placeholder no connection feeds would fail the node at render time, so
    # catch it here.
    for node in by_id.values():
        if node.get("kind") not in OUTPUT_NODE_KINDS:
            continue
        text_field = "command" if node["kind"] == "cli" else "promptTemplate"
        referenced = _template_names(node.get(text_field) or "")
        for item in node.get("inputs") or []:
            name = item.get("name") or ""
            connected = any(
                edge.get("target") == node["id"] and edge.get("targetInputId") == item.get("id") for edge in edges
            )
            if not connected and name in referenced:
                issues.append(f"'{node.get('title')}' uses {{{{{name}}}}} but nothing feeds the input '{name}'")

    if topological_order(nodes, edges) is None:
        issues.append("The graph has a circular connection")
    return issues


def _validate_output_node(node: dict[str, Any]) -> list[str]:
    """A run or cli node: named inputs, template placeholders, and its text."""
    issues: list[str] = []
    title = node.get("title") or node.get("id") or "node"
    if node["kind"] == "cli":
        text_field, label = "command", "command"
    else:
        text_field, label = "promptTemplate", "prompt"
    template = node.get(text_field) or ""
    if not template.strip():
        issues.append(f"'{title}' needs a {label}")
    names: list[str] = []
    for item in node.get("inputs") or []:
        name = item.get("name") or ""
        if not INPUT_NAME_RE.match(name):
            issues.append(f"'{title}' has an invalid input name '{name}'")
            continue
        if name in names:
            issues.append(f"'{title}' declares the input '{name}' twice")
            continue
        names.append(name)
    for name in _template_names(template):
        if name not in names:
            issues.append(f"'{title}' uses {{{{{name}}}}} but declares no input named '{name}'")
    return issues


def _validate_form_node(node: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    title = node.get("title") or node.get("id") or "form node"
    fields = node.get("fields") or []
    if not fields:
        issues.append(f"Form '{title}' needs at least one field")
        return issues
    seen: set[str] = set()
    for field in fields:
        field_title = field.get("title") or ""
        if not field_title:
            issues.append(f"Form '{title}' has a field without a title")
            continue
        if field_title in seen:
            issues.append(f"Form '{title}' has two fields titled '{field_title}'")
        seen.add(field_title)
        if field.get("type") == "select" and not (field.get("options") or []):
            issues.append(f"Field '{field_title}' is a dropdown and needs options")
        if field.get("type") in NUMERIC_FIELD_TYPES:
            low, high = field.get("min"), field.get("max")
            if low is None or high is None or low >= high:
                issues.append(f"Field '{field_title}' needs a range where min is below max")
            step = field.get("step")
            if step is not None and step <= 0:
                issues.append(f"Field '{field_title}' needs a step above zero")
    return issues


def _validate_edge(edge: dict[str, Any], by_id: dict[str, dict[str, Any]], seen_edges: set[str]) -> list[str]:
    issues: list[str] = []
    key = (
        f"{edge.get('source')}:{edge.get('sourceFieldId')}"
        f"->{edge.get('target')}:{edge.get('targetInputId') or edge.get('targetFieldId')}"
    )
    if key in seen_edges:
        issues.append("Two identical connections exist")
        return issues
    seen_edges.add(key)
    source = by_id.get(edge.get("source") or "")
    target = by_id.get(edge.get("target") or "")
    if source is None or target is None:
        issues.append("A connection points at a missing node")
        return issues
    if source is target:
        issues.append(f"'{source.get('title')}' cannot connect to itself")
        return issues
    if source.get("kind") in OUTPUT_NODE_KINDS:
        if edge.get("sourceFieldId"):
            issues.append(f"'{source.get('title')}' has no field outputs")
    elif not any(field.get("id") == edge.get("sourceFieldId") for field in source.get("fields") or []):
        issues.append(f"'{source.get('title')}' has no field for one connection")
    if target.get("kind") in OUTPUT_NODE_KINDS:
        if edge.get("targetFieldId") or not any(
            item.get("id") == edge.get("targetInputId") for item in target.get("inputs") or []
        ):
            issues.append(f"'{target.get('title')}' has no input for one incoming connection")
    elif edge.get("targetInputId") or not any(
        field.get("id") == edge.get("targetFieldId") for field in target.get("fields") or []
    ):
        issues.append(f"'{target.get('title')}' has no field for one incoming connection")
    return issues


def _template_names(template: str) -> list[str]:
    return [match.group(1) for match in TEMPLATE_RE.finditer(template or "")]


def topological_order(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> list[str] | None:
    """Node ids in dependency order, or None when the edges form a cycle."""
    ids = [node["id"] for node in nodes if node.get("id")]
    indegree = {node_id: 0 for node_id in ids}
    forward: dict[str, list[str]] = {node_id: [] for node_id in ids}
    for edge in edges:
        source, target = edge.get("source") or "", edge.get("target") or ""
        if source in indegree and target in indegree and source != target:
            forward[source].append(target)
            indegree[target] += 1
    order: list[str] = [node_id for node_id in ids if indegree[node_id] == 0]
    queue = list(order)
    while queue:
        current = queue.pop(0)
        for next_id in forward[current]:
            indegree[next_id] -= 1
            if indegree[next_id] == 0:
                order.append(next_id)
                queue.append(next_id)
    if len(order) != len(ids):
        return None
    return order


# --- template rendering ----------------------------------------------------
def render_template(template: str, values: dict[str, list[str]]) -> tuple[str, list[str]]:
    """Fill ``{{name}}`` placeholders from gathered input values.

    ``{{name}}`` joins every value with a newline, ``{{name[2]}}`` takes one
    value, and ``{{name.join(", ")}}`` joins with the given separator. Unknown
    names and out-of-range indexes are returned as errors and left in place.
    """
    errors: list[str] = []

    def replace(match: re.Match[str]) -> str:
        name, index, separator = match.group(1), match.group(2), match.group(3)
        if name not in values:
            errors.append(f"Unknown input '{name}'")
            return match.group(0)
        choices = [str(value) for value in values[name]]
        if index is not None:
            position = int(index)
            if position >= len(choices):
                errors.append(f"Input '{name}' has {len(choices)} value(s), asked for [{position}]")
                return match.group(0)
            return choices[position]
        return separator.join(choices) if separator is not None else "\n".join(choices)

    return TEMPLATE_RE.sub(replace, template or ""), errors


# --- execution -------------------------------------------------------------
# The orchestrator tasks and pending form futures live in the API process only,
# keyed by execution id (forms by (execution id, node id)).
_orchestrators: dict[str, asyncio.Task[None]] = {}
_forms: dict[tuple[str, str], asyncio.Future[None]] = {}


def _new_state(definition: dict[str, Any], order: list[str]) -> dict[str, Any]:
    return {
        "order": order,
        "nodes": {node["id"]: {"status": NODE_PENDING} for node in definition["nodes"]},
        "outputs": {},
        "formValues": {},
        "pendingForm": None,
    }


async def start_execution(session: Session, graph: ExecutionGraph, *, trigger: str) -> str:
    """Create the execution's task and row, then start orchestrating in the background.

    Raises ``ValueError`` when the definition would not run or the graph
    already has a running execution; the router turns that into a 409.
    """
    definition = normalize_definition(graph.definition)
    issues = validate_definition(definition)
    if issues:
        raise ValueError("; ".join(issues))
    if _active_execution_id(session, graph.id):
        raise ValueError(f"'{graph.name}' already has a running execution")

    from .crud import add_timeline

    task = Task(
        title=f"[Graph] {graph.name}",
        description=graph.description,
        status=TaskStatus.open,
        tags=["graph"],
    )
    session.add(task)
    session.flush()
    order = topological_order(definition["nodes"], definition["edges"]) or []
    execution = GraphExecution(
        graph_id=graph.id,
        task_id=task.id,
        trigger=trigger,
        state=_new_state(definition, order),
    )
    session.add(execution)
    graph.last_run_at = utcnow()
    if graph.enabled and graph.schedule:
        from .schedules import compute_next_run

        graph.next_run_at = compute_next_run(graph.schedule, base=graph.last_run_at, timezone=graph.timezone)
    session.add(graph)
    session.commit()
    session.refresh(execution)
    add_timeline(session, task.id, "graph_started", f"Execution graph: {graph.name}", {"execution_id": execution.id})

    # The orchestrator opens its own short sessions, like the scheduled-task
    # runner does, so it holds nothing on the caller's session.
    _start_orchestrator(execution.id)
    return execution.id


def _start_orchestrator(execution_id: str) -> None:
    task = asyncio.create_task(_orchestrate(execution_id))
    _orchestrators[execution_id] = task
    task.add_done_callback(lambda done: _orchestrators.pop(execution_id, None))


def shutdown() -> None:
    """Stop every live orchestrator. The API calls this while shutting down.

    Each task settles its own execution as cancelled through its
    ``CancelledError`` handler.
    """
    for task in list(_orchestrators.values()):
        task.cancel()
    _orchestrators.clear()


def _active_execution_id(session: Session, graph_id: str) -> str | None:
    return session.exec(
        select(GraphExecution.id)
        .where(col(GraphExecution.graph_id) == graph_id)
        .where(col(GraphExecution.status) == GraphExecutionStatus.running)
    ).first()


def active_execution_id(session: Session, graph_id: str) -> str | None:
    """The id of the graph's running execution, or None."""
    return _active_execution_id(session, graph_id)


def _save_state(execution_id: str, state: dict[str, Any]) -> None:
    with contextlib.suppress(Exception), Session(engine) as session:
        execution = session.get(GraphExecution, execution_id)
        if execution is not None:
            execution.state = state
            session.add(execution)
            session.commit()


def _read_execution(execution_id: str) -> tuple[GraphExecution, ExecutionGraph] | None:
    with Session(engine) as session:
        execution = session.get(GraphExecution, execution_id)
        graph = session.get(ExecutionGraph, execution.graph_id) if execution else None
        if execution is None or graph is None:
            return None
        session.expunge(execution)
        session.expunge(graph)
        return execution, graph


def _set_node(state: dict[str, Any], node_id: str, *, status: str, run_id: str | None = None, error: str = "") -> None:
    entry = state["nodes"].setdefault(node_id, {})
    entry["status"] = status
    if run_id is not None:
        entry["runId"] = run_id
    if error:
        entry["error"] = error[:500]
    entry.setdefault("startedAt", utcnow().isoformat())
    if status in TERMINAL_NODE_STATES:
        entry["endedAt"] = utcnow().isoformat()


def _status(state: dict[str, Any], node_id: str) -> str:
    return (state.get("nodes", {}).get(node_id) or {}).get("status", NODE_PENDING)


def _settled(state: dict[str, Any], nodes: dict[str, dict[str, Any]]) -> bool:
    return all(_status(state, node_id) in TERMINAL_NODE_STATES for node_id in nodes)


def _incoming(edges: list[dict[str, Any]], node_id: str) -> list[dict[str, Any]]:
    return [edge for edge in edges if edge.get("target") == node_id]


async def _orchestrate(execution_id: str) -> None:
    """Walk the DAG: start ready nodes, wait, and finalize the execution."""
    loaded = _read_execution(execution_id)
    if loaded is None:
        return
    _execution, graph = loaded
    definition = normalize_definition(graph.definition)
    nodes = {node["id"]: node for node in definition["nodes"]}
    edges = definition["edges"]
    state = (_execution.state or _new_state(definition, [])) if _execution else _new_state(definition, [])
    try:
        while True:
            progressed = await _advance(execution_id, nodes, edges, state)
            _save_state(execution_id, state)
            if _settled(state, nodes):
                break
            if not progressed:
                await _wait_for_progress(execution_id, nodes, state)
                state = _merged_state(execution_id, state)
    except asyncio.CancelledError:
        await _cancel_active_runs(state)
        _finalize(execution_id, GraphExecutionStatus.cancelled, "Cancelled", nodes, state)
        raise
    except Exception as exc:  # noqa: BLE001
        log.warning("graph execution failed", execution_id=execution_id, error=str(exc))
        _finalize(execution_id, GraphExecutionStatus.failed, str(exc), nodes, state)
        return
    failed = [node_id for node_id, node in nodes.items() if _status(state, node_id) == NODE_FAILED]
    if failed:
        title = nodes[failed[0]].get("title") or failed[0]
        _finalize(execution_id, GraphExecutionStatus.failed, f"Node '{title}' failed", nodes, state)
    else:
        _finalize(execution_id, GraphExecutionStatus.succeeded, "", nodes, state)


async def _advance(
    execution_id: str,
    nodes: dict[str, dict[str, Any]],
    edges: list[dict[str, Any]],
    state: dict[str, Any],
) -> bool:
    """Start every node whose dependencies just settled. True when anything moved."""
    progressed = False
    for node_id in state.get("order") or list(nodes):
        node = nodes.get(node_id)
        if node is None or _status(state, node_id) != NODE_PENDING:
            continue
        incoming = _incoming(edges, node_id)
        if any(_status(state, edge["source"]) not in TERMINAL_NODE_STATES for edge in incoming):
            continue
        if any(_status(state, edge["source"]) in (NODE_FAILED, NODE_SKIPPED) for edge in incoming):
            _set_node(state, node_id, status=NODE_SKIPPED, error="An upstream node did not finish")
            progressed = True
        elif node["kind"] == "run":
            await _start_run_node(execution_id, node, incoming, nodes, state)
            progressed = True
        elif node["kind"] == "cli":
            await _start_cli_node(execution_id, node, incoming, nodes, state)
            progressed = True
        elif await _request_form(execution_id, node, incoming, nodes, edges, state):
            progressed = True
    return progressed


def _input_values(
    node: dict[str, Any], incoming: list[dict[str, Any]], nodes: dict[str, dict[str, Any]], state: dict[str, Any]
) -> dict[str, list[str]]:
    """The values each declared input receives, in edge order."""
    values: dict[str, list[str]] = {}
    for edge in incoming:
        input_name = next(
            (item["name"] for item in node.get("inputs") or [] if item.get("id") == (edge.get("targetInputId") or "")),
            "",
        )
        if not input_name:
            continue
        source = nodes.get(edge.get("source") or "")
        if source is None:
            continue
        if source.get("kind") in OUTPUT_NODE_KINDS:
            value = str(state.get("outputs", {}).get(source["id"], ""))
        else:
            field_values = state.get("formValues", {}).get(source["id"]) or {}
            value = str(field_values.get(edge.get("sourceFieldId") or "", ""))
        values.setdefault(input_name, []).append(value)
    return values


def _resolve_cwd(session: Session, task: Task, explicit: str) -> str:
    """The directory a run node executes in: the node's own, else the task's."""
    from pathlib import Path

    if explicit:
        return str(Path(explicit).expanduser())
    from .models.repositories import Repository, TaskRepository, Worktree

    active = session.exec(
        select(Worktree)
        .where(Worktree.task_id == task.id, col(Worktree.status) == "active")
        .order_by(col(Worktree.created_at).desc())
    ).first()
    if active is not None:
        return active.path
    link = session.exec(
        select(TaskRepository).where(TaskRepository.task_id == task.id).order_by(col(TaskRepository.created_at))
    ).first()
    if link is not None:
        repo = session.get(Repository, link.repository_id)
        if repo is not None:
            return repo.path
    settings.worktree_root.mkdir(parents=True, exist_ok=True)
    return str(settings.worktree_root)


async def _start_run_node(
    execution_id: str,
    node: dict[str, Any],
    incoming: list[dict[str, Any]],
    nodes: dict[str, dict[str, Any]],
    state: dict[str, Any],
) -> None:
    """Render the prompt and enqueue the run. A render or enqueue error fails the node."""
    prompt, errors = render_template(node.get("promptTemplate") or "", _input_values(node, incoming, nodes, state))
    if errors:
        _set_node(state, node["id"], status=NODE_FAILED, error="; ".join(errors))
        return
    try:
        with Session(engine) as session:
            execution = session.get(GraphExecution, execution_id)
            task = session.get(Task, execution.task_id) if execution else None
            if task is None:
                _set_node(state, node["id"], status=NODE_FAILED, error="The execution's task is gone")
                return
            from .agents.harnesses import get_harness

            harness = get_harness(session, node.get("harnessId") or None)
            run = AgentRun(
                task_id=task.id,
                harness_id=harness.id,
                cwd=_resolve_cwd(session, task, node.get("cwd") or ""),
                prompt=prompt,
                kind="graph",
                requested_model=node.get("model") or None,
                graph_execution_id=execution_id,
                graph_node_id=node["id"],
                status=RunStatus.queued,
            )
            session.add(run)
            session.commit()
            session.refresh(run)
            run_id = run.id
        from .jobs import enqueue_run

        await enqueue_run(run_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("failed to start graph run node", execution_id=execution_id, node=node["id"], error=str(exc))
        _set_node(state, node["id"], status=NODE_FAILED, error=str(exc))
        return
    _set_node(state, node["id"], status=NODE_RUNNING, run_id=run_id)


def _cli_binary() -> str:
    """The `agentic` console script: the venv's own first, then PATH."""
    import shutil
    import sys
    from pathlib import Path

    sibling = Path(sys.executable).with_name("agentic")
    if sibling.is_file():
        return str(sibling)
    return shutil.which("agentic") or "agentic"


async def _run_cli(argv: list[str], cwd: str, env: dict[str, str]) -> tuple[int | None, str]:
    """Run one agentic CLI invocation to completion; (exit code, combined output).

    The child is killed when the orchestrator task is cancelled, so stopping an
    execution does not leave CLI processes behind.
    """
    proc = await asyncio.create_subprocess_exec(
        *argv,
        cwd=cwd or None,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), settings.scheduled_task_timeout or None)
    except TimeoutError:
        proc.kill()
        with contextlib.suppress(Exception):
            await proc.wait()
        return None, f"Timed out after {settings.scheduled_task_timeout}s"
    except asyncio.CancelledError:
        proc.kill()
        with contextlib.suppress(Exception):
            await proc.wait()
        raise
    return proc.returncode, stdout.decode("utf-8", "replace")


async def _start_cli_node(
    execution_id: str,
    node: dict[str, Any],
    incoming: list[dict[str, Any]],
    nodes: dict[str, dict[str, Any]],
    state: dict[str, Any],
) -> None:
    """Run one agentic CLI command with the rendered command line.

    The node's output is the command's stdout (JSON with ``--format json``),
    which downstream inputs consume like a run's answer. A non-zero exit, a
    render error, or a timeout fails the node.
    """
    command, errors = render_template(node.get("command") or "", _input_values(node, incoming, nodes, state))
    try:
        tokens = shlex.split(command) if not errors else []
    except ValueError as exc:
        # An unbalanced quote in the rendered command line.
        tokens, errors = [], [str(exc)]
    if errors or not tokens:
        detail = "; ".join(errors) or "The command is empty"
        _set_node(state, node["id"], status=NODE_FAILED, error=detail)
        return
    argv = [_cli_binary(), "--api-url", _self_api_url(), "--format", "json", *tokens]
    env = {**os.environ, "AGENTIC_API_URL": _self_api_url()}
    _set_node(state, node["id"], status=NODE_RUNNING)
    try:
        exit_code, output = await _run_cli(argv, node.get("cwd") or "", env)
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001
        log.warning("cli node failed", execution_id=execution_id, node=node["id"], error=str(exc))
        _set_node(state, node["id"], status=NODE_FAILED, error=str(exc))
        return
    output = output[:MAX_OUTPUT]
    if exit_code == 0:
        state.setdefault("outputs", {})[node["id"]] = output
        _set_node(state, node["id"], status=NODE_DONE)
    else:
        detail = f"exit {exit_code}: {output[-400:]}" if output else f"exit {exit_code}"
        _set_node(state, node["id"], status=NODE_FAILED, error=detail)


def _self_api_url() -> str:
    """The URL CLI nodes use to reach this very server."""
    return os.environ.get("AGENTIC_API_URL") or "http://127.0.0.1:8600"


def _run_consumers(
    node: dict[str, Any], edges: list[dict[str, Any]], nodes: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """The run nodes directly downstream of this form node."""
    consumers: list[dict[str, Any]] = []
    for edge in edges:
        target = edge.get("target") or ""
        if edge.get("source") != node["id"] or target not in nodes:
            continue
        if nodes[target]["kind"] in OUTPUT_NODE_KINDS:
            consumers.append(nodes[target])
    return consumers


def _form_needed(
    node: dict[str, Any], edges: list[dict[str, Any]], nodes: dict[str, dict[str, Any]], state: dict[str, Any]
) -> bool:
    """True when a downstream run is otherwise ready and still waiting on us.

    A form is requested only then, so the user never answers a dialog whose
    consumer already failed; a form whose consumers all failed or were skipped
    is skipped instead.
    """
    for consumer in _run_consumers(node, edges, nodes):
        if _status(state, consumer["id"]) != NODE_PENDING:
            continue
        others = [edge for edge in _incoming(edges, consumer["id"]) if edge.get("source") != node["id"]]
        if all(_status(state, edge["source"]) == NODE_DONE for edge in others):
            return True
    return False


async def _request_form(
    execution_id: str,
    node: dict[str, Any],
    incoming: list[dict[str, Any]],
    nodes: dict[str, dict[str, Any]],
    edges: list[dict[str, Any]],
    state: dict[str, Any],
) -> bool:
    """Mark the form waiting and record its request, or skip it. True when it moved."""
    consumers = _run_consumers(node, edges, nodes)
    if not consumers or not any(
        _status(state, consumer["id"]) in (NODE_PENDING, NODE_RUNNING) for consumer in consumers
    ):
        _set_node(state, node["id"], status=NODE_SKIPPED, error="No downstream run needs this form")
        return True
    if not _form_needed(node, edges, nodes, state):
        # A consumer is still working on its other inputs; ask again when it is.
        return False
    defaults: dict[str, str] = {}
    for edge in incoming:
        field_id = edge.get("targetFieldId") or ""
        source = nodes.get(edge.get("source") or "")
        if not field_id or source is None:
            continue
        if source.get("kind") == "run":
            value = str(state.get("outputs", {}).get(source["id"], ""))
        else:
            value = str((state.get("formValues", {}).get(source["id"]) or {}).get(edge.get("sourceFieldId") or "", ""))
        defaults[field_id] = value[:MAX_OUTPUT]
    # Fields nothing injects fall back to their own declared default, so the
    # dialog never opens empty.
    for field in node.get("fields") or []:
        defaults.setdefault(field.get("id") or "", str(field.get("defaultValue") or ""))
    state["pendingForm"] = {"nodeId": node["id"], "requestedAt": utcnow().isoformat(), "defaults": defaults}
    _set_node(state, node["id"], status=NODE_WAITING)
    future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
    _forms[(execution_id, node["id"])] = future
    return True


async def _wait_for_progress(execution_id: str, nodes: dict[str, dict[str, Any]], state: dict[str, Any]) -> None:
    """Sleep until a form was answered or a running run may have settled."""
    running = [
        node_id for node_id, node in nodes.items() if node["kind"] == "run" and _status(state, node_id) == NODE_RUNNING
    ]
    waiting = [node_id for node_id, node in nodes.items() if _status(state, node_id) == NODE_WAITING]
    futures = [future for future in (_forms.get((execution_id, node_id)) for node_id in waiting) if future]
    if not futures and waiting and not running:
        # A form whose answer request was lost can never proceed; fail loudly
        # instead of spinning.
        raise RuntimeError(f"The form on node '{waiting[0]}' has no pending request to answer")
    if futures and running:
        timer = asyncio.create_task(asyncio.sleep(POLL_SECONDS))
        await asyncio.wait([*futures, timer], return_when=asyncio.FIRST_COMPLETED)
        timer.cancel()
    elif futures:
        await asyncio.wait(futures, return_when=asyncio.FIRST_COMPLETED)
    else:
        await asyncio.sleep(POLL_SECONDS)
    for node_id in running:
        _refresh_run_node(node_id, state)


def _refresh_run_node(node_id: str, state: dict[str, Any]) -> None:
    """Move a running node to done/failed once its run row settles, capturing output."""
    run_id = (state["nodes"].get(node_id) or {}).get("runId")
    if not run_id or _status(state, node_id) != NODE_RUNNING:
        return
    with Session(engine) as session:
        run = session.get(AgentRun, run_id)
        if run is None:
            _set_node(state, node_id, status=NODE_FAILED, error="The run row disappeared")
            return
        if run.status in (RunStatus.queued, RunStatus.running):
            return
        if run.status == RunStatus.succeeded:
            state.setdefault("outputs", {})[node_id] = _run_output(session, run_id)
            _set_node(state, node_id, status=NODE_DONE)
        else:
            _set_node(state, node_id, status=NODE_FAILED, error=run.error or f"The run {run.status.value}")


def _run_output(session: Session, run_id: str) -> str:
    """A run's final answer: its messages, falling back to its thoughts."""
    events = session.exec(select(AgentEvent).where(AgentEvent.run_id == run_id).order_by(col(AgentEvent.seq))).all()
    text = "".join(event.text for event in events if event.type == "message")
    if not text.strip():
        text = "".join(event.text for event in events if event.type == "thought")
    return text[:MAX_OUTPUT]


def _merged_state(execution_id: str, state: dict[str, Any]) -> dict[str, Any]:
    """Fold the form answers the endpoint stored into the working state."""
    with Session(engine) as session:
        execution = session.get(GraphExecution, execution_id)
        stored = (execution.state or {}) if execution else {}
    for node_id, values in (stored.get("formValues") or {}).items():
        state.setdefault("formValues", {}).setdefault(node_id, values)
    for node_id, node_state in (stored.get("nodes") or {}).items():
        stored_status = node_state.get("status")
        if stored_status in (NODE_DONE, NODE_FAILED) and _status(state, node_id) == NODE_WAITING:
            _set_node(state, node_id, status=stored_status, error=node_state.get("error") or "")
            state["pendingForm"] = None
    return state


async def submit_form(execution_id: str, node_id: str, values: dict[str, str], *, cancel: bool = False) -> bool:
    """Answer a pending form (or cancel it, which fails it). True when accepted."""
    loaded = _read_execution(execution_id)
    if loaded is None:
        return False
    execution, _graph = loaded
    if execution.status != GraphExecutionStatus.running:
        return False
    pending = (execution.state or {}).get("pendingForm") or {}
    if pending.get("nodeId") != node_id:
        return False
    with Session(engine) as session:
        execution = session.get(GraphExecution, execution_id)
        if execution is None:
            return False
        # A fresh dict assigned back to the column: in-place edits of a JSON
        # column are invisible to SQLAlchemy's change tracking.
        state = dict(execution.state or {})
        state["formValues"] = dict(state.get("formValues") or {})
        state["formValues"][node_id] = dict(values)
        state["pendingForm"] = None
        state["nodes"] = dict(state.get("nodes") or {})
        entry = dict(state["nodes"].get(node_id) or {})
        entry["status"] = NODE_FAILED if cancel else NODE_DONE
        if cancel:
            entry["error"] = "The form was cancelled"
        state["nodes"][node_id] = entry
        execution.state = state
        session.add(execution)
        session.commit()
    future = _forms.pop((execution_id, node_id), None)
    if future is not None and not future.done():
        future.set_result(None)
    return True


async def cancel_execution(execution_id: str) -> bool:
    """Cancel a running execution: stop the walk and abort its active runs."""
    loaded = _read_execution(execution_id)
    if loaded is None:
        return False
    execution, _graph = loaded
    if execution.status != GraphExecutionStatus.running:
        return False
    orchestrator = _orchestrators.get(execution_id)
    if orchestrator is not None:
        orchestrator.cancel()
        # Settle before answering, so the caller sees the cancelled row.
        await asyncio.gather(orchestrator, return_exceptions=True)
        return True
    # No live orchestrator (lost to a restart reconciliation missed): settle
    # the row and its runs here.
    state = execution.state or {}
    await _cancel_active_runs(state)
    _finalize(execution_id, GraphExecutionStatus.cancelled, "Cancelled", {}, state)
    return True


async def _cancel_active_runs(state: dict[str, Any]) -> None:
    from .jobs import cancel_run as cancel_queued_run

    for node_state in (state.get("nodes") or {}).values():
        run_id = node_state.get("runId")
        if not run_id or node_state.get("status") != NODE_RUNNING:
            continue
        with contextlib.suppress(Exception):
            await cancel_queued_run(run_id)
        node_state["status"] = NODE_SKIPPED
        node_state["error"] = "Cancelled"


def _release_form(execution_id: str, state: dict[str, Any]) -> None:
    """Drop a still-pending form request when the execution ends."""
    pending = state.get("pendingForm") or {}
    if pending.get("nodeId"):
        future = _forms.pop((execution_id, pending["nodeId"]), None)
        if future is not None and not future.done():
            future.set_result(None)
        state["pendingForm"] = None


def _finalize(
    execution_id: str,
    status: GraphExecutionStatus,
    error: str,
    nodes: dict[str, dict[str, Any]],
    state: dict[str, Any],
) -> None:
    """Settle the execution row and note the outcome on its task's timeline."""
    from .crud import add_timeline

    with contextlib.suppress(Exception), Session(engine) as session:
        execution = session.get(GraphExecution, execution_id)
        if execution is None:
            return
        if state.get("pendingForm"):
            _release_form(execution_id, state)
        if nodes:
            for node_id, node in nodes.items():
                if node["kind"] == "form" and _status(state, node_id) == NODE_WAITING:
                    _set_node(state, node_id, status=NODE_SKIPPED, error="The execution ended")
        execution.status = status
        execution.error = error
        execution.ended_at = utcnow()
        execution.state = state
        session.add(execution)
        session.commit()
        add_timeline(
            session,
            execution.task_id,
            "graph_finished",
            f"Graph execution {status.value}" + (f": {error}" if error else ""),
            {"execution_id": execution_id},
        )


# --- cron scheduling -------------------------------------------------------
async def run_due_once() -> int:
    """Fire every enabled graph whose next occurrence has passed.

    The occurrence is advanced before the execution starts, so a slow one is
    never fired twice; when the previous execution still runs, the fire is
    skipped and only the schedule moves on.
    """
    now = utcnow()
    with Session(engine) as session:
        due = session.exec(
            select(ExecutionGraph)
            .where(col(ExecutionGraph.enabled) == True)  # noqa: E712
            .where(col(ExecutionGraph.schedule).is_not(None), col(ExecutionGraph.schedule) != "")
            .where(or_(col(ExecutionGraph.next_run_at).is_(None), col(ExecutionGraph.next_run_at) <= now))
        ).all()
        graph_ids = [graph.id for graph in due]
    started = 0
    from .schedules import compute_next_run

    for graph_id in graph_ids:
        with Session(engine) as session:
            graph = session.get(ExecutionGraph, graph_id)
            if graph is None or not graph.enabled or not graph.schedule:
                continue
            graph.last_run_at = utcnow()
            graph.next_run_at = compute_next_run(graph.schedule, base=graph.last_run_at, timezone=graph.timezone)
            busy = _active_execution_id(session, graph.id) is not None
            session.add(graph)
            session.commit()
            if busy:
                log.info("skipped graph execution, one is already running", graph_id=graph_id)
                continue
            session.refresh(graph)
            await start_execution(session, graph, trigger="schedule")
        started += 1
    return started


async def scheduler_loop() -> None:
    """Tick on a timer and fire the graphs that are due."""
    tick = settings.scheduled_task_tick
    if tick <= 0:
        return
    while True:
        await asyncio.sleep(tick)
        try:
            started = await run_due_once()
        except Exception as exc:  # noqa: BLE001
            log.warning("graph scheduler tick failed", error=str(exc))
            continue
        if started:
            log.info("started graph executions", count=started)


def reconcile_graph_executions() -> int:
    """Mark executions left ``running`` by a previous process as failed.

    The walk lives in the API process, so a restart loses it. The runs it had
    enqueued are SAQ jobs and finish on their own; only the walk is lost.
    """
    recovered = 0
    with Session(engine) as session:
        stale = session.exec(
            select(GraphExecution).where(col(GraphExecution.status) == GraphExecutionStatus.running)
        ).all()
        for execution in stale:
            execution.status = GraphExecutionStatus.failed
            execution.error = "Interrupted by a server restart"
            execution.ended_at = utcnow()
            session.add(execution)
            recovered += 1
        if recovered:
            session.commit()
    if recovered:
        log.info("marked interrupted graph executions as failed", count=recovered)
    return recovered
