"""Agentic user CLI.

A thin, scriptable client over the Agentic HTTP API, meant to be driven by
people and by agents. This is the user-facing client; the backend (running the
server) lives in ``agentic.server_cli``.

Commands return data; use ``--format json`` (or pipe the output, which selects
json automatically) for machine-readable results.

    agentic task create --title "Fix flaky tests"
    agentic link add <task> --source github --url https://github.com/o/r/issues/1
    agentic worktree create <task>
    agentic context refresh <task>
    agentic run create <task> --prompt "Investigate the failure"
    agentic run wait <run-id>
"""

from __future__ import annotations

import functools
import json
import os
import sys
import time
from typing import Annotated, Any, Literal

from cyclopts import App, Parameter
from rich.console import Console

from .client import DEFAULT_API_URL, AgenticClient, ApiError

CONTEXT: dict[str, Any] = {
    "api_url": os.environ.get("AGENTIC_API_URL", DEFAULT_API_URL),
    "format": os.environ.get("AGENTIC_FORMAT", "auto"),
    "timeout": float(os.environ.get("AGENTIC_TIMEOUT", "60")),
    # Who is driving the CLI. The harness sets AGENTIC_ACTOR=agent for the agent
    # process it spawns, so the server can tell agent work from human work.
    "actor": os.environ.get("AGENTIC_ACTOR", "human"),
}

TaskStatus = Literal["open", "in_progress", "blocked", "done", "archived"]
Source = Literal["slack", "github", "gdrive", "url", "note", "commit", "file"]


# --- infrastructure -------------------------------------------------------
def _resolve_format() -> str:
    fmt = CONTEXT["format"]
    if fmt == "auto":
        return "text" if sys.stdout.isatty() else "json"
    return fmt


def emit(data: Any, text: str | None = None) -> str:
    if _resolve_format() == "json":
        return json.dumps(data, indent=2, default=str)
    return text if text is not None else json.dumps(data, indent=2, default=str)


def _client() -> AgenticClient:
    return AgenticClient(CONTEXT["api_url"], timeout=CONTEXT["timeout"], actor=CONTEXT["actor"])


def safe(fn):
    """Turn API errors into a one-line stderr message and a non-zero exit code."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ApiError as exc:
            print(f"error: {exc.detail} (HTTP {exc.status_code})", file=sys.stderr)
            return 1
        except KeyboardInterrupt:
            print("interrupted", file=sys.stderr)
            return 130

    return wrapper


# --- renderers ------------------------------------------------------------
def _join(rows: list, render) -> str:
    return "\n".join(render(row) for row in rows) if rows else "(none)"


def _task_line(task: dict) -> str:
    line = f"{task['id']}  [{task['status']}] p{task['priority']}  {task['title']}"
    tags = task.get("tags") or []
    if tags:
        line += "  " + " ".join(f"#{tag}" for tag in tags)
    if task.get("deadline"):
        line += f"  due {task['deadline'][:16]}"
    return line


def _task_text(task: dict) -> str:
    lines = [_task_line(task)]
    if task.get("people"):
        lines.append("  people: " + ", ".join(person["name"] for person in task["people"]))
    if task.get("requesters"):
        lines.append("  requested by: " + ", ".join(person["name"] for person in task["requesters"]))
    for session in task.get("sessions") or []:
        lines.append(f"  session: {session['session_id']} ({session['id']})")
    if task.get("summary"):
        lines.append(f"  summary: {task['summary']}")
    for step in task.get("next_steps") or []:
        lines.append(f"  [{'x' if step.get('done') else ' '}] {step.get('text')}")
    return "\n".join(lines)


def _item_line(item: dict) -> str:
    return f"{item['id']}  {item['source']:<7} {item.get('title') or item.get('url') or ''}"


def _run_line(run: dict) -> str:
    return f"{run['id']}  {run['status']:<10} {run['kind']:<15} {run['prompt'][:60]}"


def _run_text(run: dict) -> str:
    lines = [_run_line(run)]
    if run.get("session_id"):
        lines.append(f"  session: {run['session_id']}")
    if run.get("cwd"):
        lines.append(f"  cwd: {run['cwd']}")
    for link in run.get("links") or []:
        lines.append(f"  {link['label']}: {link.get('url') or link.get('command')}")
    return "\n".join(lines)


def _session_line(session: dict) -> str:
    label = session.get("label") or ""
    return f"{session['id']}  {session['session_id']}  {label}".rstrip()


def _session_text(session: dict) -> str:
    lines = [_session_line(session)]
    if session.get("harness_id"):
        lines.append(f"  harness: {session['harness_id']}")
    if session.get("cwd"):
        lines.append(f"  cwd: {session['cwd']}")
    for link in session.get("links") or []:
        lines.append(f"  {link['label']}: {link.get('url') or link.get('command')}")
    return "\n".join(lines)


def _deps_text(deps: dict) -> str:
    lines = []
    for label in ("before", "after"):
        tasks = deps.get(label) or []
        lines.append(f"{label}:")
        if tasks:
            lines.extend(f"  {_task_line(task)}" for task in tasks)
        else:
            lines.append("  (none)")
    return "\n".join(lines)


def _graph_text(data: dict) -> str:
    lines = [f"nodes: {len(data.get('nodes') or [])}  edges: {len(data.get('edges') or [])}"]
    lines.extend(f"{edge['before_id']} -> {edge['after_id']}" for edge in data.get("edges") or [])
    return "\n".join(lines)


# --- app ------------------------------------------------------------------
# Plain console: no Rich markup (so `[open]` stays literal) and no wrapping
# (so json output stays valid when piped).
_CONSOLE = Console(markup=False, highlight=False, soft_wrap=True)

app = App(
    name="agentic",
    help="Drive the Agentic app (tasks, items, agents) from the command line.",
    console=_CONSOLE,
)
app.meta.console = _CONSOLE


@app.meta.default
def _launcher(
    *tokens: Annotated[str, Parameter(show=False, allow_leading_hyphen=True)],
    api_url: str = DEFAULT_API_URL,
    format: Literal["auto", "json", "text"] = "auto",
    timeout: float = 60.0,
) -> Any:
    """Agentic CLI.

    Parameters
    ----------
    api_url
        Base URL of the Agentic API (default: $AGENTIC_API_URL or 127.0.0.1:8600).
    format
        Output format. `auto` uses json when stdout is not a terminal.
    timeout
        Per-request timeout in seconds.
    """
    CONTEXT.update(api_url=api_url, format=format, timeout=timeout)
    # Nested dispatch returns the command's value; return it so the meta app
    # prints it (and turns int results into exit codes).
    return app(tokens)


# --- health ---------------------------------------------------------------
@app.command(name="health")
@safe
def health() -> str:
    """Check that the API is reachable."""
    with _client() as client:
        data = client.health()
    return emit(data, f"{data.get('status')} ({data.get('service')}) at {CONTEXT['api_url']}")


# --- tasks -------------------------------------------------------------
task_app = App(name="task", help="Create and manage tasks.")
app.command(task_app)


@task_app.command(name="list")
@safe
def task_list(status: TaskStatus | None = None, q: str | None = None, tag: list[str] | None = None) -> str:
    """List tasks, newest first (optionally filtered by --tag, repeatable)."""
    with _client() as client:
        tasks = client.list_tasks(status=status, q=q, tags=tag)
    return emit(tasks, _join(tasks, _task_line))


@task_app.command(name="deadlines")
@safe
def task_deadlines(within_days: int = 7) -> str:
    """List in-flight tasks with a deadline coming up (overdue included)."""
    with _client() as client:
        tasks = client.list_deadlines(within_days=within_days)
    return emit(tasks, _join(tasks, _task_line))


@task_app.command(name="get")
@safe
def task_get(task_id: str) -> str:
    """Show a task with its items, worktrees, runs, and timeline."""
    with _client() as client:
        task = client.get_task(task_id)
    return emit(task, _task_text(task))


@task_app.command(name="create")
@safe
def task_create(
    title: str = "",
    description: str = "",
    priority: int = 2,
    status: TaskStatus = "open",
    tags: list[str] | None = None,
    deadline: str | None = None,
    repository_ids: list[str] | None = None,
    group_id: str | None = None,
    harness_id: str | None = None,
    github_url: str | None = None,
    slack_url: str | None = None,
) -> str:
    """Create a task.

    Import one from a GitHub issue with --github-url, or from a Slack thread
    with --slack-url (an agent then names it and summarizes the discussion).
    Set a deadline with --deadline (an ISO 8601 date or date-time).
    """
    with _client() as client:
        task = client.create_task(
            title=title,
            description=description,
            priority=priority,
            status=status,
            tags=tags,
            deadline=deadline,
            repository_ids=repository_ids,
            group_id=group_id,
            harness_id=harness_id,
            github_url=github_url,
            slack_url=slack_url,
        )
    return emit(task, f"created {task['id']}  {task['title']}")


@task_app.command(name="update")
@safe
def task_update(
    task_id: str,
    title: str | None = None,
    description: str | None = None,
    status: TaskStatus | None = None,
    priority: int | None = None,
    tags: list[str] | None = None,
    deadline: str | None = None,
    clear_deadline: bool = False,
    repository_ids: list[str] | None = None,
    harness_id: str | None = None,
    summary: str | None = None,
) -> str:
    """Update a task's fields.

    Set a deadline with --deadline (an ISO 8601 date or date-time), or remove it
    with --clear-deadline.
    """
    with _client() as client:
        task = client.update_task(
            task_id,
            title=title,
            description=description,
            status=status,
            priority=priority,
            tags=tags,
            deadline=deadline,
            repository_ids=repository_ids,
            harness_id=harness_id,
            summary=summary,
        )
        if clear_deadline:
            task = client.set_task_deadline(task_id, None)
    return emit(task, f"updated {task['id']}  {_task_line(task)}")


@task_app.command(name="delete")
@safe
def task_delete(task_id: str) -> str:
    """Delete a task and everything attached to it."""
    with _client() as client:
        client.delete_task(task_id)
    return emit({"deleted": task_id}, f"deleted {task_id}")


@task_app.command(name="timeline")
@safe
def task_timeline(task_id: str) -> str:
    """Show a task's timeline."""
    with _client() as client:
        events = client.task_timeline(task_id)
    text = _join(events, lambda e: f"{e['created_at'][:19]}  {e['type']:<18} {e['message']}")
    return emit(events, text)


@task_app.command(name="link")
@safe
def task_link(task_id: str, related_id: str, relation: Literal["before", "after"] = "after") -> str:
    """Link a related task before or after this one.

    `--relation before` means the related task must be done first; `after` means
    it follows this one. A link that would close a cycle is refused.
    """
    with _client() as client:
        deps = client.add_dependency(task_id, related_id, relation)
    return emit(deps, _deps_text(deps))


@task_app.command(name="unlink")
@safe
def task_unlink(task_id: str, related_id: str) -> str:
    """Remove the before/after link between two tasks."""
    with _client() as client:
        client.remove_dependency(task_id, related_id)
    return emit({"unlinked": related_id}, f"unlinked {related_id} from {task_id}")


@task_app.command(name="deps")
@safe
def task_deps(task_id: str) -> str:
    """Show the tasks linked before and after this one."""
    with _client() as client:
        deps = client.task_dependencies(task_id)
    return emit(deps, _deps_text(deps))


# --- graph ----------------------------------------------------------------
@app.command(name="graph")
@safe
def graph(include_done: bool = False) -> str:
    """Show the before/after graph: every task and the edges between them."""
    with _client() as client:
        data = client.get_graph(include_done=include_done)
    return emit(data, _graph_text(data))


# --- tags -----------------------------------------------------------------
tag_app = App(name="tag", help="Inspect the tags carried by tasks.")
app.command(tag_app)


@tag_app.command(name="list")
@safe
def tag_list() -> str:
    """List the tags in use, with how many tasks carry each."""
    with _client() as client:
        tags = client.list_tags()
    return emit(tags, _join(tags, lambda t: f"{t['name']}  ({t['count']})"))


# --- people ---------------------------------------------------------------
person_app = App(name="person", help="Create and manage people and their links.")
app.command(person_app)


def _person_line(person: dict) -> str:
    return f"{person['id']}  {person['name']}  tasks:{person['task_count']} items:{person['item_count']}"


def _person_text(person: dict) -> str:
    lines = [_person_line(person)]
    if person.get("aliases"):
        lines.append("  aliases: " + ", ".join(person["aliases"]))
    if person.get("notes"):
        lines.append(f"  notes: {person['notes']}")
    if person.get("task_ids"):
        lines.append("  tasks: " + ", ".join(person["task_ids"]))
    if person.get("item_ids"):
        lines.append("  items: " + ", ".join(person["item_ids"]))
    return "\n".join(lines)


@person_app.command(name="list")
@safe
def person_list() -> str:
    """List people with their task and item counts."""
    with _client() as client:
        people = client.list_people()
    return emit(people, _join(people, _person_line))


@person_app.command(name="get")
@safe
def person_get(person_id: str) -> str:
    """Show a person and what they are linked to."""
    with _client() as client:
        person = client.get_person(person_id)
    return emit(person, _person_text(person))


@person_app.command(name="create")
@safe
def person_create(
    *,
    name: str,
    aliases: list[str] | None = None,
    notes: str = "",
) -> str:
    """Create a person. Pass --aliases once per handle or email."""
    with _client() as client:
        person = client.create_person(name=name, aliases=aliases, notes=notes)
    return emit(person, f"created {person['id']}  {person['name']}")


@person_app.command(name="update")
@safe
def person_update(
    person_id: str,
    *,
    name: str | None = None,
    aliases: list[str] | None = None,
    notes: str | None = None,
) -> str:
    """Update a person's fields. --aliases replaces the whole list."""
    with _client() as client:
        person = client.update_person(person_id, name=name, aliases=aliases, notes=notes)
    return emit(person, f"updated {person['id']}  {_person_line(person)}")


@person_app.command(name="delete")
@safe
def person_delete(person_id: str) -> str:
    """Delete a person and their links."""
    with _client() as client:
        client.delete_person(person_id)
    return emit({"deleted": person_id}, f"deleted {person_id}")


@person_app.command(name="merge")
@safe
def person_merge(source_id: str, *, into: str) -> str:
    """Merge a person into another (--into), which absorbs their aliases and links."""
    with _client() as client:
        person = client.merge_person(source_id, into)
    return emit(person, f"merged {source_id} into {person['id']}  {person['name']}")


@person_app.command(name="link")
@safe
def person_link(
    person_id: str,
    *,
    task: str | None = None,
    item: str | None = None,
    requested_by: str | None = None,
) -> str | int:
    """Link a person to a task (--task), an item (--item), or as the requester of a task (--requested-by TASK)."""
    if requested_by:
        with _client() as client:
            person = client.link_requester(person_id, requested_by)
        return emit(person, f"linked {person['id']} as a requester of task {requested_by}")
    if not task and not item:
        print("error: provide --task, --item, or --requested-by", file=sys.stderr)
        return 1
    with _client() as client:
        person = client.link_person(person_id, task_id=task, item_id=item)
    target = f"task {task}" if task else f"item {item}"
    return emit(person, f"linked {person['id']} to {target}")


@person_app.command(name="unlink")
@safe
def person_unlink(
    person_id: str,
    *,
    task: str | None = None,
    item: str | None = None,
    requested_by: str | None = None,
) -> str | int:
    """Unlink a person from a task (--task), an item (--item), or a task they requested (--requested-by TASK)."""
    if requested_by:
        with _client() as client:
            client.unlink_requester(person_id, requested_by)
        return emit({"unlinked": person_id}, f"unlinked {person_id} as a requester of task {requested_by}")
    if not task and not item:
        print("error: provide --task, --item, or --requested-by", file=sys.stderr)
        return 1
    with _client() as client:
        client.unlink_person(person_id, task_id=task, item_id=item)
    target = f"task {task}" if task else f"item {item}"
    return emit({"unlinked": person_id}, f"unlinked {person_id} from {target}")


# --- changes --------------------------------------------------------------
ChangeStatusArg = Literal["proposed", "verified", "accepted", "rejected", "reverted"]
ChangeClassArg = Literal["feature", "bugfix", "refactor", "chore", "docs", "test", "trivial"]
InterventionArg = Literal["question", "correction", "manual_fix", "rerun", "approval", "other"]

change_app = App(name="change", help="Record the factory changes the metrics are computed from.")
app.command(change_app)


def _change_line(change: dict) -> str:
    touch = "touched  " if change.get("human_intervened") else "touchless"
    return (
        f"{change['id']}  {change['status']:<9} {change.get('change_class', ''):<8} {touch} {change.get('title') or ''}"
    )


def _change_text(change: dict) -> str:
    lines = [_change_line(change)]
    if change.get("external_ref"):
        lines.append(f"  ref: {change['external_ref']}")
    for key in ("opened_at", "verified_at", "accepted_at", "closed_at"):
        if change.get(key):
            lines.append(f"  {key}: {change[key]}")
    if change.get("notes"):
        lines.append(f"  notes: {change['notes']}")
    for intervention in change.get("interventions") or []:
        lines.append(f"  intervention [{intervention['kind']}] {intervention.get('note') or ''}")
    return "\n".join(lines)


@change_app.command(name="list")
@safe
def change_list(
    task_id: str | None = None,
    status: ChangeStatusArg | None = None,
    change_class: ChangeClassArg | None = None,
) -> str:
    """List changes, newest first."""
    with _client() as client:
        changes = client.list_changes(task_id=task_id, status=status, change_class=change_class)
    return emit(changes, _join(changes, _change_line))


@change_app.command(name="get")
@safe
def change_get(change_id: str) -> str:
    """Show a change with its interventions."""
    with _client() as client:
        change = client.get_change(change_id)
    return emit(change, _change_text(change))


@change_app.command(name="create")
@safe
def change_create(
    task_id: str,
    title: str = "",
    change_class: ChangeClassArg = "feature",
    external_ref: str | None = None,
    repository_id: str | None = None,
    worktree_id: str | None = None,
    notes: str = "",
) -> str:
    """Record a change against a task."""
    with _client() as client:
        change = client.create_change(
            task_id=task_id,
            title=title,
            change_class=change_class,
            external_ref=external_ref,
            repository_id=repository_id,
            worktree_id=worktree_id,
            notes=notes,
        )
    return emit(change, f"created change {change['id']}  {_change_line(change)}")


def _transition(change_id: str, status: str) -> str:
    with _client() as client:
        change = client.transition_change(change_id, status)
    return emit(change, f"{status}: {_change_line(change)}")


@change_app.command(name="verify")
@safe
def change_verify(change_id: str) -> str:
    """Mark a change verified."""
    return _transition(change_id, "verified")


@change_app.command(name="accept")
@safe
def change_accept(change_id: str) -> str:
    """Mark a change accepted (reached production)."""
    return _transition(change_id, "accepted")


@change_app.command(name="reject")
@safe
def change_reject(change_id: str) -> str:
    """Reject a change before acceptance."""
    return _transition(change_id, "rejected")


@change_app.command(name="revert")
@safe
def change_revert(change_id: str) -> str:
    """Mark an accepted change reverted (it did not survive observation)."""
    return _transition(change_id, "reverted")


@change_app.command(name="intervene")
@safe
def change_intervene(change_id: str, kind: InterventionArg = "other", note: str = "") -> str:
    """Record a human intervention, which makes the change non-touchless."""
    with _client() as client:
        intervention = client.add_intervention(change_id, kind=kind, note=note)
    return emit(intervention, f"intervened ({kind}) on {change_id}")


@change_app.command(name="delete")
@safe
def change_delete(change_id: str) -> str:
    """Delete a change and its interventions."""
    with _client() as client:
        client.delete_change(change_id)
    return emit({"deleted": change_id}, f"deleted {change_id}")


# --- metrics --------------------------------------------------------------
def _metrics_text(report: dict) -> str:
    lines = [
        f"window {report['window_days']}d  observation {report['observation_days']}d  tolerance {report['tolerance']}"
    ]
    for metric in report["metrics"]:
        value = "n/a" if metric["value"] is None else f"{metric['value']:.1%}"
        baseline = "none" if metric["baseline"] is None else f"{metric['baseline']:.1%}"
        delta = "" if metric["delta"] is None else f" ({metric['delta']:+.1%})"
        lines.append(
            f"{metric['label']:<14} {value:>6}  [{metric['direction']}]  "
            f"baseline {baseline}{delta}  ({metric['numerator']}/{metric['denominator']})"
        )
    counts = report["counts"]
    lines.append(
        f"changes: accepted {counts['accepted']}, touchless {counts['touchless']}, "
        f"reverted {counts['reverted']}, rejected {counts['rejected']}, "
        f"pending {counts['pending_observation']}, open {counts['open']}"
    )
    return "\n".join(lines)


metrics_app = App(name="metrics", help="Read autonomy rate and yield, and manage their baselines.")
app.command(metrics_app)


@metrics_app.command(name="show")
@safe
def metrics_show(
    window_days: int = 30,
    observation_days: int = 14,
    tolerance: float = 0.02,
    task_id: str | None = None,
    change_class: ChangeClassArg | None = None,
) -> str:
    """Show autonomy rate and yield with their direction against the baseline."""
    with _client() as client:
        report = client.get_metrics(
            window_days=window_days,
            observation_days=observation_days,
            tolerance=tolerance,
            task_id=task_id,
            change_class=change_class,
        )
    return emit(report, _metrics_text(report))


baseline_app = App(name="baseline", help="Read and set the baseline each metric is compared against.")
metrics_app.command(baseline_app)


@baseline_app.command(name="list")
@safe
def baseline_list() -> str:
    """List the stored metric baselines."""
    with _client() as client:
        baselines = client.list_baselines()
    return emit(baselines, _join(baselines, lambda b: f"{b['metric']}  {b['value']:.1%}  {b['captured_at'][:19]}"))


@baseline_app.command(name="set")
@safe
def baseline_set(
    metric: Literal["autonomy_rate", "yield"],
    value: float,
    window_days: int = 30,
    observation_days: int = 14,
    note: str = "",
) -> str:
    """Set a metric's baseline to the value you measured before the factory run."""
    with _client() as client:
        baseline = client.set_baseline(
            metric, value, window_days=window_days, observation_days=observation_days, note=note
        )
    return emit(baseline, f"{baseline['metric']} baseline = {baseline['value']:.1%}")


@baseline_app.command(name="delete")
@safe
def baseline_delete(metric: Literal["autonomy_rate", "yield"]) -> str:
    """Clear a metric's baseline."""
    with _client() as client:
        client.delete_baseline(metric)
    return emit({"deleted": metric}, f"deleted baseline {metric}")


# --- items ----------------------------------------------------------------
item_app = App(name="item", help="Create and manage source items (Slack/GitHub/Drive/URL/note).")
app.command(item_app)


@item_app.command(name="list")
@safe
def item_list(source: Source | None = None) -> str:
    """List items."""
    with _client() as client:
        items = client.list_items(source=source)
    return emit(items, _join(items, _item_line))


@item_app.command(name="get")
@safe
def item_get(item_id: str) -> str:
    """Show an item."""
    with _client() as client:
        item = client.get_item(item_id)
    return emit(item, _item_line(item))


@item_app.command(name="create")
@safe
def item_create(
    source: Source | None = None,
    url: str | None = None,
    title: str = "",
    content: str = "",
    external_id: str | None = None,
    fetch: bool = True,
) -> str:
    """Create an item (source is inferred from the url/content; fetches unless --no-fetch)."""
    with _client() as client:
        item = client.create_item(
            source=source, url=url, title=title, content=content, external_id=external_id, fetch=fetch
        )
    return emit(item, f"created {item['id']}  {_item_line(item)}")


@item_app.command(name="refresh")
@safe
def item_refresh(item_id: str) -> str:
    """Re-fetch an item's metadata/content."""
    with _client() as client:
        item = client.refresh_item(item_id)
    return emit(item, f"refreshed {item['id']}  {_item_line(item)}")


@item_app.command(name="refresh-due")
@safe
def item_refresh_due() -> str:
    """Re-fetch the Slack/GitHub items the refresh policy says are due."""
    with _client() as client:
        report = client.refresh_due_items()
    text = (
        f"checked {report['checked']}  due {report['due']}  refreshed {report['refreshed']}  failed {report['failed']}"
    )
    for entry in report.get("items") or []:
        marker = "ok" if entry.get("refreshed") else "fail"
        text += f"\n  {marker}  {entry['source']}  {entry['title'] or entry['item_id']}"
    return emit(report, text)


@item_app.command(name="refresh-source")
@safe
def item_refresh_source(source: str) -> str:
    """Re-fetch every item of one source now, ignoring the refresh policy."""
    with _client() as client:
        report = client.refresh_source(source)
    text = f"checked {report['checked']}  refreshed {report['refreshed']}  failed {report['failed']}"
    for entry in report.get("items") or []:
        marker = "ok" if entry.get("refreshed") else "fail"
        text += f"\n  {marker}  {entry['title'] or entry['item_id']}"
    return emit(report, text)


@item_app.command(name="delete")
@safe
def item_delete(item_id: str) -> str:
    """Delete an item and its associations."""
    with _client() as client:
        client.delete_item(item_id)
    return emit({"deleted": item_id}, f"deleted {item_id}")


# --- links ----------------------------------------------------------------
link_app = App(name="link", help="Associate items with tasks.")
app.command(link_app)


@link_app.command(name="add")
@safe
def link_add(
    task_id: str,
    item_id: str | None = None,
    source: Source | None = None,
    url: str | None = None,
    title: str = "",
    content: str = "",
    external_id: str | None = None,
    note: str = "",
    fetch: bool = True,
) -> str | int:
    """Associate an existing item (--item-id) or a new one (--url/--content) with a task."""
    item = None
    if item_id is None:
        if not (url or content or title):
            print("error: provide --item-id, or a --url/--content for a new item", file=sys.stderr)
            return 1
        item = {
            "source": source,
            "url": url,
            "title": title,
            "content": content,
            "external_id": external_id,
            "fetch": fetch,
        }
    with _client() as client:
        association = client.associate(task_id, item_id=item_id, item=item, note=note)
    return emit(association, f"linked {association['item']['id']} to {task_id}")


@link_app.command(name="remove")
@safe
def link_remove(task_id: str, item_id: str) -> str:
    """Remove an item's association with a task."""
    with _client() as client:
        client.unassociate(task_id, item_id)
    return emit({"unlinked": item_id}, f"unlinked {item_id} from {task_id}")


# --- repositories ---------------------------------------------------------
repository_app = App(name="repository", help="Register local git repositories.")
app.command(repository_app)


@repository_app.command(name="list")
@safe
def repository_list() -> str:
    """List repositories."""
    with _client() as client:
        repos = client.list_repositories()
    return emit(repos, _join(repos, lambda r: f"{r['id']}  {r['name']}  {r['path']}"))


@repository_app.command(name="add")
@safe
def repository_add(path: str, name: str | None = None) -> str:
    """Register a local git repository by path."""
    with _client() as client:
        repo = client.add_repository(path, name=name)
    return emit(repo, f"added {repo['id']}  {repo['name']}  {repo['path']}")


@repository_app.command(name="remove")
@safe
def repository_remove(repository_id: str) -> str:
    """Remove a repository (files are not touched)."""
    with _client() as client:
        client.remove_repository(repository_id)
    return emit({"removed": repository_id}, f"removed {repository_id}")


# --- worktrees ------------------------------------------------------------
worktree_app = App(name="worktree", help="Create isolated git worktrees for tasks.")
app.command(worktree_app)


@worktree_app.command(name="list")
@safe
def worktree_list(task_id: str) -> str:
    """List a task's worktrees."""
    with _client() as client:
        worktrees = client.list_worktrees(task_id)
    return emit(worktrees, _join(worktrees, lambda w: f"{w['id']}  [{w['status']}] {w['branch']}  {w['path']}"))


@worktree_app.command(name="create")
@safe
def worktree_create(
    task_id: str,
    repository_id: str | None = None,
    branch: str | None = None,
    base: str | None = None,
) -> str:
    """Create a worktree for a task."""
    with _client() as client:
        worktree = client.create_worktree(task_id, repository_id=repository_id, branch=branch, base=base)
    return emit(worktree, f"created worktree {worktree['id']}  {worktree['branch']}  {worktree['path']}")


@worktree_app.command(name="remove")
@safe
def worktree_remove(task_id: str, worktree_id: str) -> str:
    """Remove a worktree from disk and stop tracking it."""
    with _client() as client:
        client.remove_worktree(task_id, worktree_id)
    return emit({"removed": worktree_id}, f"removed worktree {worktree_id}")


# --- runs -----------------------------------------------------------------
run_app = App(name="run", help="Start, watch, and inspect agent runs.")
app.command(run_app)


@run_app.command(name="list")
@safe
def run_list(task_id: str) -> str:
    """List a task's agent runs."""
    with _client() as client:
        runs = client.list_runs(task_id)
    return emit(runs, _join(runs, _run_line))


@run_app.command(name="get")
@safe
def run_get(run_id: str) -> str:
    """Show a run, including its session links."""
    with _client() as client:
        run = client.get_run(run_id)
    return emit(run, _run_text(run))


@run_app.command(name="events")
@safe
def run_events(run_id: str) -> str:
    """Show a run's transcript."""
    with _client() as client:
        events = client.run_events(run_id)
    text = _join(events, lambda e: f"[{e['type']}] {e['text']}")
    return emit(events, text)


@run_app.command(name="create")
@safe
def run_create(
    task_id: str,
    prompt: str,
    harness_id: str | None = None,
    worktree_id: str | None = None,
    cwd: str | None = None,
) -> str:
    """Start an agent run against a task."""
    with _client() as client:
        run = client.create_run(task_id, prompt, harness_id=harness_id, worktree_id=worktree_id, cwd=cwd)
    return emit(run, f"started run {run['id']} ({run['status']}) in {run.get('cwd')}")


@run_app.command(name="cancel")
@safe
def run_cancel(run_id: str) -> str:
    """Cancel a running agent."""
    with _client() as client:
        run = client.cancel_run(run_id)
    return emit(run, f"cancelling {run_id}")


@run_app.command(name="wait")
@safe
def run_wait(run_id: str, timeout: float = 600.0, interval: float = 2.0) -> str:
    """Block until a run finishes, then print it."""
    terminal = {"succeeded", "failed", "cancelled"}
    deadline = time.monotonic() + timeout
    with _client() as client:
        while True:
            run = client.get_run(run_id)
            if run["status"] in terminal:
                return emit(run, _run_text(run))
            if time.monotonic() >= deadline:
                return emit(run, f"still {run['status']} after {timeout:.0f}s (run {run_id})")
            time.sleep(interval)


@run_app.command(name="stream")
@safe
def run_stream(run_id: str) -> None:
    """Stream a run's events live (json lines or plain text)."""
    machine = _resolve_format() == "json"
    with _client() as client:
        for event in client.stream_run(run_id):
            if machine:
                print(json.dumps(event, default=str))
            else:
                print(f"[{event.get('type')}] {event.get('text', '')}")
            if event.get("type") == "run_finished":
                break


# --- sessions -------------------------------------------------------------
session_app = App(name="session", help="Record agent sessions against tasks and reopen them.")
app.command(session_app)


@session_app.command(name="list")
@safe
def session_list(task_id: str) -> str:
    """List a task's recorded agent sessions."""
    with _client() as client:
        sessions = client.list_sessions(task_id)
    return emit(sessions, _join(sessions, _session_line))


@session_app.command(name="get")
@safe
def session_get(task_id: str, session_id: str) -> str:
    """Show a recorded session and how to reopen it."""
    with _client() as client:
        session = client.get_session(task_id, session_id)
    return emit(session, _session_text(session))


@session_app.command(name="add")
@safe
def session_add(
    task_id: str,
    session_id: str,
    harness_id: str | None = None,
    cwd: str | None = None,
    label: str = "",
) -> str:
    """Attach an existing agent session to a task.

    Use this for a session agentic did not start, such as one opened in
    OpenChamber. --harness-id and --cwd feed the resume command and the
    OpenChamber link; the harness defaults to the task's harness.
    """
    with _client() as client:
        session = client.create_session(task_id, session_id, harness_id=harness_id, cwd=cwd, label=label)
    return emit(session, f"attached session {session['id']}  {session['session_id']}")


@session_app.command(name="update")
@safe
def session_update(
    task_id: str,
    session_id: str,
    harness_id: str | None = None,
    cwd: str | None = None,
    label: str | None = None,
) -> str:
    """Update a recorded session's label, working directory, or harness."""
    with _client() as client:
        session = client.update_session(task_id, session_id, harness_id=harness_id, cwd=cwd, label=label)
    return emit(session, f"updated session {session['id']}  {_session_line(session)}")


@session_app.command(name="remove")
@safe
def session_remove(task_id: str, session_id: str) -> str:
    """Remove a recorded session from a task (the session itself is untouched)."""
    with _client() as client:
        client.delete_session(task_id, session_id)
    return emit({"removed": session_id}, f"removed session {session_id}")


# --- context --------------------------------------------------------------
context_app = App(name="context", help="Read or refresh a task's agent-maintained context.")
app.command(context_app)


@context_app.command(name="get")
@safe
def context_get(task_id: str) -> str:
    """Show a task's current summary and next steps."""
    with _client() as client:
        context = client.get_context(task_id)
    text = context.get("summary", "")
    for step in context.get("next_steps") or []:
        text += f"\n- [{'x' if step.get('done') else ' '}] {step.get('text')}"
    return emit(context, text or "(no context yet)")


@context_app.command(name="refresh")
@safe
def context_refresh(task_id: str) -> str:
    """Ask an agent to rewrite the summary and next steps."""
    with _client() as client:
        run = client.refresh_context(task_id)
    return emit(run, f"context refresh started: run {run['id']}")


# --- harnesses ------------------------------------------------------------
harness_app = App(name="harness", help="Inspect and configure agent harnesses.")
app.command(harness_app)


@harness_app.command(name="list")
@safe
def harness_list() -> str:
    """List harnesses, whether they are on PATH, and which is the default."""
    with _client() as client:
        harnesses = client.list_harnesses()
    text = _join(
        harnesses,
        lambda h: (
            f"{'*' if h.get('is_default') else ' '} {h['id']:<10} "
            f"{'available' if h['available'] else 'missing':<10} {h.get('detail', '')}"
        ),
    )
    return emit(harnesses, text)


@harness_app.command(name="create")
@safe
def harness_create(
    name: str,
    command: str,
    args: list[str] | None = None,
    description: str = "",
    resume_command: str | None = None,
    model: str | None = None,
) -> str:
    """Add an ACP harness."""
    with _client() as client:
        harness = client.create_harness(
            name=name,
            command=command,
            args=args or [],
            description=description,
            resume_command=resume_command,
            model=model,
        )
    return emit(harness, f"created harness {harness['id']}  {harness['command']}")


@harness_app.command(name="update")
@safe
def harness_update(
    harness_id: str,
    name: str | None = None,
    command: str | None = None,
    args: list[str] | None = None,
    resume_command: str | None = None,
    model: str | None = None,
) -> str:
    """Update a harness."""
    with _client() as client:
        harness = client.update_harness(
            harness_id, name=name, command=command, args=args, resume_command=resume_command, model=model
        )
    return emit(harness, f"updated harness {harness['id']}")


@harness_app.command(name="delete")
@safe
def harness_delete(harness_id: str) -> str:
    """Delete a harness."""
    with _client() as client:
        client.delete_harness(harness_id)
    return emit({"deleted": harness_id}, f"deleted {harness_id}")


# --- settings -------------------------------------------------------------
settings_app = App(name="settings", help="Read and update app settings.")
app.command(settings_app)


@settings_app.command(name="get")
@safe
def settings_get() -> str:
    """Show effective settings and their overrides."""
    with _client() as client:
        settings = client.get_settings()
    effective = settings["effective"]
    text = "\n".join(f"{key} = {value!r}" for key, value in effective.items())
    return emit(settings, text)


@settings_app.command(name="refresh-status")
@safe
def settings_refresh_status() -> str:
    """Show when the background refresh job last ran for each source."""
    with _client() as client:
        status = client.refresh_status()
    sources = status.get("sources") or {}
    lines = [
        f"{source}: {entry.get('last_run_at') or 'never'}  ({entry.get('refreshed', 0)} refreshed)"
        for source, entry in sources.items()
    ]
    return emit(status, "\n".join(lines) or "no background runs recorded")


@settings_app.command(name="set")
@safe
def settings_set(
    openchamber_url: str | None = None,
    openchamber_session_path: str | None = None,
    terminal_url_template: str | None = None,
    slack_refresh_policy: str | None = None,
    github_refresh_policy: str | None = None,
) -> str:
    """Override settings (empty disables a link or a source's refresh; policies look like 1d=1h,7d=6h,30d=1d,*=7d)."""
    values: dict[str, Any] = {
        "openchamber_url": openchamber_url,
        "openchamber_session_path": openchamber_session_path,
        "terminal_url_template": terminal_url_template,
        "slack_refresh_policy": slack_refresh_policy,
        "github_refresh_policy": github_refresh_policy,
    }
    with _client() as client:
        settings = client.update_settings(**values)
    effective = settings["effective"]
    text = "\n".join(f"{key} = {value!r}" for key, value in effective.items())
    return emit(settings, text)


# --- stack (focus queue) --------------------------------------------------
stack_app = App(name="stack", help="Work the focus stack: the current task and the queue below it.")
app.command(stack_app)


def _format_duration(seconds: float) -> str:
    total = max(0, int(seconds))
    minutes, sec = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    if days > 0:
        return f"{days}d {hours:02d}h"
    if hours > 0:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m {sec:02d}s"


def _stack_line(entry: dict) -> str:
    task = entry.get("task") or {}
    marker = "*" if entry.get("is_current") else " "
    count = entry.get("execution_count") or 0
    return (
        f"{marker} {entry['position']}  {task.get('title') or entry.get('task_id')}  "
        f"x{count}  {_format_duration(entry.get('duration') or 0)}"
    )


@stack_app.command(name="list")
@safe
def stack_list() -> str:
    """Show the stack, the current task first."""
    with _client() as client:
        entries = client.list_stack()
    return emit(entries, _join(entries, _stack_line))


@stack_app.command(name="current")
@safe
def stack_current() -> str:
    """Show the current task (the top of the stack)."""
    with _client() as client:
        entry = client.stack_current()
    if entry is None:
        return emit(None, "(stack is empty)")
    return emit(entry, _stack_line(entry))


@stack_app.command(name="history")
@safe
def stack_history() -> str:
    """Show the soft-deleted stack history, most recent first."""
    with _client() as client:
        entries = client.stack_history()
    return emit(entries, _join(entries, _stack_line))


@stack_app.command(name="push")
@safe
def stack_push(
    title: str = "",
    description: str = "",
    position: Literal["top", "next", "last"] = "top",
    task_id: str | None = None,
) -> str | int:
    """Add a task to the stack: a new one (--title) or an existing --task-id.

    --position picks where it lands: top (becomes current), next (after the
    current task), or last (the bottom of the queue).
    """
    if not title.strip() and not task_id:
        print("error: provide --title or --task-id", file=sys.stderr)
        return 1
    with _client() as client:
        entries = client.push_stack(title=title, description=description, position=position, task_id=task_id)
    return emit(entries, _join(entries, _stack_line))


@stack_app.command(name="pop")
@safe
def stack_pop() -> str:
    """Pop the current task (mark it done) and promote the next one."""
    with _client() as client:
        entries = client.pop_stack()
    return emit(entries, _join(entries, _stack_line))


@stack_app.command(name="promote")
@safe
def stack_promote(entry_id: str) -> str:
    """Move an entry to the top of the stack (make it the current task)."""
    with _client() as client:
        entries = client.promote_stack(entry_id)
    return emit(entries, _join(entries, _stack_line))


@stack_app.command(name="reorder")
@safe
def stack_reorder(entry_id: str, position: int) -> str:
    """Move an entry to a new position (0 is the current task)."""
    with _client() as client:
        entries = client.reorder_stack(entry_id, position)
    return emit(entries, _join(entries, _stack_line))


@stack_app.command(name="edit")
@safe
def stack_edit(entry_id: str, title: str | None = None, description: str | None = None) -> str:
    """Edit the task behind an entry (its title and/or description)."""
    with _client() as client:
        entries = client.update_stack_entry(entry_id, title=title, description=description)
    return emit(entries, _join(entries, _stack_line))


@stack_app.command(name="remove")
@safe
def stack_remove(entry_id: str) -> str:
    """Remove an entry from the stack (soft delete; the task is kept)."""
    with _client() as client:
        client.remove_stack_entry(entry_id)
    return emit({"removed": entry_id}, f"removed {entry_id}")


# --- operations (provenance audit log) ------------------------------------
def _operation_line(operation: dict) -> str:
    when = str(operation.get("created_at") or "")[:19]
    return (
        f"{when}  {operation['method']:<6} {operation['status_code']}  "
        f"{operation['client']:<4} {operation['actor']:<5}  {operation['path']}"
    )


operation_app = App(name="operation", help="Read the audit log of mutating operations.")
app.command(operation_app)


@operation_app.command(name="list")
@safe
def operation_list(
    client: Literal["web", "cli", "api"] | None = None,
    actor: Literal["human", "agent"] | None = None,
    limit: int = 100,
) -> str:
    """List recorded operations, newest first."""
    with _client() as c:
        operations = c.list_operations(client=client, actor=actor, limit=limit)
    return emit(operations, _join(operations, _operation_line))


def main() -> None:
    app.meta()


if __name__ == "__main__":
    main()
