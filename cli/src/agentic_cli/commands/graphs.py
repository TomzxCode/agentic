"""CLI commands."""

from __future__ import annotations

import json
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
        A 5-field cron expression to run it automatically; omitted means manual only.
    timezone
        IANA zone the cron is read in, for example ``Europe/Paris``. Defaults to the server's zone.
    disabled
        Create the graph paused instead of enabled.
    definition
        Path to a JSON file holding ``{"nodes": [...], "edges": [...]}``, as the web editor saves it.
    """
    with runtime._client() as client:
        graph = client.create_graph(
            name,
            description=description,
            schedule=schedule,
            timezone=timezone,
            enabled=not disabled,
            definition=_load_definition(definition),
        )
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
    """Update a graph's fields, or enable/disable it.

    Parameters
    ----------
    graph_id
        The graph id, as shown by ``graph list``.
    name
        New label.
    description
        New description.
    schedule
        New 5-field cron expression; pass an empty string to run only by hand.
    timezone
        New IANA zone the cron is read in.
    enable
        Turn the graph's schedule on.
    disable
        Turn the graph's schedule off.
    definition
        Path to a JSON file with a new ``{"nodes": [...], "edges": [...]}`` definition.
    """
    fields: dict[str, Any] = {
        "name": name,
        "description": description,
        "schedule": schedule,
        "timezone": timezone,
    }
    if definition:
        fields["definition"] = _load_definition(definition)
    if enable:
        fields["enabled"] = True
    if disable:
        fields["enabled"] = False
    with runtime._client() as client:
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
