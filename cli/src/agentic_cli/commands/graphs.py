"""CLI commands."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from cyclopts import App

from .. import runtime
from ..render import (
    _execution_graph_line,
    _execution_graph_text,
    _graph_execution_line,
    _graph_execution_text,
    _join,
)
from ..runtime import (
    emit,
    safe,
)

graph_app = App(name="graphs", help="Create and run execution graphs of agent runs.")


def register(app: App) -> None:
    app.command(graph_app)


def _load_definition(path: str | None) -> dict | None:
    """Read a definition JSON file ('{"nodes": [...], "edges": [...]}')."""
    if not path:
        return None
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError) as exc:
        raise ValueError(f"Could not read definition from {path}: {exc}") from exc


def _schedule_node(definition: dict, cron: str, timezone: str | None, *, enabled: bool = True) -> dict:
    """A schedule trigger node for the definition, with a free title and spot.

    A schedule is a node like any other step, so the CLI adds it to the
    definition the graph is created or updated with rather than setting a
    trigger on the graph.
    """
    nodes = definition.get("nodes") or []
    title = "Schedule"
    suffix = 2
    while any(node.get("title") == title for node in nodes):
        title = f"Schedule {suffix}"
        suffix += 1
    y = max([float((node.get("position") or {}).get("y") or 0) for node in nodes] or [0.0]) + 120
    return {
        "id": f"n{uuid.uuid4().hex[:12]}",
        "kind": "trigger",
        "triggerType": "schedule",
        "title": title,
        "position": {"x": 40.0, "y": y},
        "schedule": cron.strip(),
        "timezone": (timezone or "").strip(),
        "enabled": enabled,
        "outputs": [],
    }


def _add_schedule_node(definition: dict | None, cron: str, timezone: str | None, *, enabled: bool = True) -> dict:
    definition = definition or {"nodes": [], "edges": []}
    definition = {**definition, "nodes": [*(definition.get("nodes") or [])]}
    definition["nodes"].append(_schedule_node(definition, cron, timezone, enabled=enabled))
    return definition


def _replace_schedules(definition: dict, cron: str, timezone: str | None) -> dict:
    """Drop every schedule trigger node, then add the one the flags describe."""
    nodes = [
        node
        for node in definition.get("nodes") or []
        if not (node.get("kind") == "trigger" and node.get("triggerType") == "schedule")
    ]
    trimmed = {**definition, "nodes": nodes}
    if not cron.strip():
        return trimmed
    return _add_schedule_node(trimmed, cron, timezone)


def _set_schedules_enabled(definition: dict, enabled: bool) -> dict:
    nodes = []
    for node in definition.get("nodes") or []:
        if node.get("kind") == "trigger" and node.get("triggerType") == "schedule":
            nodes.append({**node, "enabled": enabled})
        else:
            nodes.append(node)
    return {**definition, "nodes": nodes}


@graph_app.command(name="list")
@safe
def graph_list() -> str:
    """List execution graphs, soonest next run first."""
    with runtime._client() as client:
        graphs = client.list_graphs()
    return emit(graphs, _join(graphs, _execution_graph_line))


@graph_app.command(name="get")
@safe
def graph_get(graph_id: str) -> str:
    """Show one execution graph.

    Parameters
    ----------
    graph_id
        The graph id, as shown by ``graph list``.
    """
    with runtime._client() as client:
        graph = client.get_execution_graph(graph_id)
    return emit(graph, _execution_graph_text(graph))


@graph_app.command(name="create")
@safe
def graph_create(
    name: str,
    description: str | None = None,
    schedule: str | None = None,
    timezone: str | None = None,
    disabled: bool = False,
    definition: str | None = None,
) -> str:
    """Create an execution graph.

    Parameters
    ----------
    name
        A label for the graph.
    description
        What the graph does.
    schedule
        A 5-field cron expression; adds a schedule trigger node to the definition.
    timezone
        IANA zone that cron is read in, for example ``Europe/Paris``. Defaults to the server's zone.
    disabled
        Add the schedule trigger paused instead of enabled.
    definition
        Path to a JSON file holding ``{"nodes": [...], "edges": [...]}``, as the web editor saves it.
    """
    built = _load_definition(definition) if definition else None
    if schedule is not None and schedule.strip():
        built = _add_schedule_node(built, schedule, timezone, enabled=not disabled)
    with runtime._client() as client:
        graph = client.create_graph(name, description=description, definition=built)
    return emit(graph, f"created {_execution_graph_line(graph)}")


@graph_app.command(name="update")
@safe
def graph_update(
    graph_id: str,
    *,
    name: str | None = None,
    description: str | None = None,
    schedule: str | None = None,
    timezone: str | None = None,
    enable: bool = False,
    disable: bool = False,
    definition: str | None = None,
) -> str:
    """Update a graph's fields, its schedule trigger nodes, or pause them.

    Parameters
    ----------
    graph_id
        The graph id, as shown by ``graph list``.
    name
        New label.
    description
        New description.
    schedule
        Replace every schedule trigger node with one using this 5-field cron
        expression; pass an empty string to remove every schedule.
    timezone
        IANA zone the schedule is read in, used with ``schedule``.
    enable
        Turn every schedule trigger node on.
    disable
        Turn every schedule trigger node off.
    definition
        Path to a JSON file with a new ``{"nodes": [...], "edges": [...]}`` definition.
    """
    if enable and disable:
        raise ValueError("Pass only one of --enable and --disable")
    fields: dict[str, Any] = {"name": name, "description": description}
    edited = _load_definition(definition) if definition else None
    if schedule is not None:
        edited = _replace_schedules(edited or {"nodes": [], "edges": []}, schedule, timezone)
    with runtime._client() as client:
        if enable or disable:
            current = client.get_execution_graph(graph_id)
            edited = _set_schedules_enabled(edited or current.get("definition") or {"nodes": [], "edges": []}, enable)
        if edited is not None:
            fields["definition"] = edited
        graph = client.update_graph(graph_id, **fields)
    return emit(graph, _execution_graph_text(graph))


@graph_app.command(name="delete")
@safe
def graph_delete(graph_id: str) -> str:
    """Delete an execution graph and its execution history. Past runs stay on their tasks.

    Parameters
    ----------
    graph_id
        The graph id, as shown by ``graph list``.
    """
    with runtime._client() as client:
        client.delete_graph(graph_id)
    return emit({"deleted": graph_id}, f"deleted {graph_id}")


@graph_app.command(name="run")
@safe
def graph_run(graph_id: str) -> str:
    """Run an execution graph now, in the background.

    Parameters
    ----------
    graph_id
        The graph id, as shown by ``graph list``.
    """
    with runtime._client() as client:
        execution = client.run_graph(graph_id)
    return emit(execution, f"started execution {_graph_execution_line(execution)}")


@graph_app.command(name="executions")
@safe
def graph_executions(execution_id: str | None = None, limit: int = 100) -> str:
    """Show execution history: one execution in detail, or every graph's, newest first.

    Parameters
    ----------
    execution_id
        Show this execution's nodes and outputs. Omit it to list recent executions.
    limit
        Maximum number of executions to list.
    """
    with runtime._client() as client:
        if execution_id:
            execution = client.get_graph_execution(execution_id)
            return emit(execution, _graph_execution_text(execution))
        executions = client.graph_executions(limit=limit)
    return emit(executions, _join(executions, _graph_execution_line))
