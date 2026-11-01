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


def _load_triggers(path: str | None) -> list[dict] | None:
    """Read a trigger list JSON file ('[{"type": "schedule", "config": {...}}]')."""
    if not path:
        return None
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, ValueError) as exc:
        raise ValueError(f"Could not read triggers from {path}: {exc}") from exc
    if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
        raise ValueError(f"Triggers in {path} must be a JSON list of objects")
    return data


def _shortcut_triggers(schedule: str | None, timezone: str | None, webhook: bool) -> list[dict]:
    """The triggers the simple flags describe: one schedule and/or one webhook."""
    built: list[dict] = []
    if schedule is not None and schedule.strip():
        built.append({"type": "schedule", "config": {"cron": schedule.strip(), "timezone": (timezone or "").strip()}})
    if webhook:
        built.append({"type": "webhook", "config": {}})
    return built


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
    webhook: bool = False,
    triggers: str | None = None,
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
        A 5-field cron expression for a schedule trigger; omitted adds no schedule.
    timezone
        IANA zone that cron is read in, for example ``Europe/Paris``. Defaults to the server's zone.
    webhook
        Also add a webhook trigger, fired by an HTTP call to its URL.
    triggers
        Path to a JSON file holding a list of triggers, for types the flags do not cover.
        Takes precedence over the ``schedule``, ``timezone``, and ``webhook`` shortcuts.
    disabled
        Create the triggers paused instead of enabled.
    definition
        Path to a JSON file holding ``{"nodes": [...], "edges": [...]}``, as the web editor saves it.
    """
    built = (_load_triggers(triggers) if triggers else None) or _shortcut_triggers(schedule, timezone, webhook)
    if disabled:
        built = [{**trigger, "enabled": False} for trigger in built]
    with runtime._client() as client:
        graph = client.create_graph(
            name,
            description=description,
            triggers=built or None,
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
    triggers: str | None = None,
    enable: bool = False,
    disable: bool = False,
    definition: str | None = None,
) -> str:
    """Update a graph's fields, its triggers, or pause its triggers.

    Parameters
    ----------
    graph_id
        The graph id, as shown by ``graph list``.
    name
        New label.
    description
        New description.
    schedule
        Replace every trigger with one schedule trigger using this 5-field cron
        expression; pass an empty string to remove every trigger.
    timezone
        IANA zone the schedule is read in, used with ``schedule``.
    triggers
        Path to a JSON file holding the new list of triggers; replaces every
        existing trigger, and takes precedence over ``schedule``.
    enable
        Turn every trigger on.
    disable
        Turn every trigger off.
    definition
        Path to a JSON file with a new ``{"nodes": [...], "edges": [...]}`` definition.
    """
    fields: dict[str, Any] = {
        "name": name,
        "description": description,
    }
    if definition:
        fields["definition"] = _load_definition(definition)
    if triggers is not None:
        fields["triggers"] = _load_triggers(triggers)
    elif schedule is not None:
        fields["triggers"] = _shortcut_triggers(schedule, timezone, False)
    if enable and disable:
        raise ValueError("Pass only one of --enable and --disable")
    with runtime._client() as client:
        if enable or disable:
            submitted = fields.get("triggers")
            if submitted is None:
                current = client.get_execution_graph(graph_id)
                submitted = [
                    {
                        "id": trigger.get("id", ""),
                        "type": trigger.get("type", ""),
                        "config": trigger.get("config") or {},
                        "enabled": True,
                    }
                    for trigger in current.get("triggers") or []
                ]
            fields["triggers"] = [{**trigger, "enabled": enable and not disable} for trigger in submitted or []]
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
