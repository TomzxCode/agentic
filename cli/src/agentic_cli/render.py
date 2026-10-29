"""Plain-text renderers for the CLI commands."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo


def _join(rows: list, render) -> str:
    return "\n".join(render(row) for row in rows) if rows else "(none)"


def _format_deadline(iso: str) -> str:
    return iso[:16].replace("T", " ")


def _is_future(iso: str) -> bool:
    try:
        value = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return False
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value > datetime.now(UTC)


def _task_line(task: dict) -> str:
    line = f"{task['id']}  [{task['status']}] p{task['priority']}  {task['title']}"
    tags = task.get("tags") or []
    if tags:
        line += "  " + " ".join(f"#{tag}" for tag in tags)
    if task.get("deadline"):
        line += f"  due {_format_deadline(task['deadline'])}"
    if task.get("waiting_on_person_id"):
        who = task.get("waiting_on_name") or task["waiting_on_person_id"]
        line += f"  waiting on {who}"
        if task.get("follow_up_at"):
            line += f" (check back {_format_deadline(task['follow_up_at'])})"
    if task.get("snoozed_until") and _is_future(task["snoozed_until"]):
        line += f"  snoozed until {_format_deadline(task['snoozed_until'])}"
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
    checklist = task.get("checklist") or []
    if checklist:
        lines.append("  checklist:")
        for item in checklist:
            mark = "x" if item.get("done") else " "
            suffix = "" if item.get("applicable", True) else " (no longer applies)"
            lines.append(f"    [{mark}] {item['text']}{suffix}")
    return "\n".join(lines)


def _item_line(item: dict) -> str:
    return f"{item['id']}  {item['source']:<7} {item.get('title') or item.get('url') or ''}"


def _run_line(run: dict) -> str:
    return f"{run['id']}  {run['status']:<10} {run['kind']:<15} {run['prompt'][:60]}"


def _run_text(run: dict) -> str:
    lines = [_run_line(run)]
    if run.get("model"):
        # The harness's label for the model, with the id it selects with when the
        # harness named it something else.
        label = run.get("model_name") or run["model"]
        suffix = f" ({run['model']})" if run.get("model_name") and run["model_name"] != run["model"] else ""
        lines.append(f"  model: {label}{suffix}")
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
    for label in ("before", "after", "related"):
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


def _person_line(person: dict) -> str:
    return f"{person['id']}  {person['name']}  tasks:{person['task_count']} items:{person['item_count']}"


def _person_text(person: dict) -> str:
    lines = [_person_line(person)]
    if person.get("aliases"):
        lines.append("  aliases: " + ", ".join(person["aliases"]))
    for note in person.get("notes") or []:
        stamp = str(note.get("created_at") or "")[:19].replace("T", " ")
        lines.append(f"  note {stamp}: {note.get('content') or ''}".rstrip())
    if person.get("task_ids"):
        lines.append("  tasks: " + ", ".join(person["task_ids"]))
    if person.get("item_ids"):
        lines.append("  items: " + ", ".join(person["item_ids"]))
    return "\n".join(lines)


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


def _hours_text(hours: float | None) -> str:
    """A duration in hours, rendered in the largest unit that keeps it readable."""
    if hours is None:
        return "n/a"
    if hours < 1:
        return f"{hours * 60:.0f}m"
    if hours < 48:
        return f"{hours:.1f}h"
    return f"{hours / 24:.1f}d"


def _cycle_time_text(report: dict) -> str:
    lines = [f"window {report['window_days']}d  buckets {report['bucket_days']}d"]
    if not report["repositories"]:
        lines.append("No repository with a GitHub remote.")
        return "\n".join(lines)
    for repository in report["repositories"]:
        heading = f"{repository['name']}"
        if repository.get("full_name"):
            heading += f"  ({repository['full_name']})"
        lines.append(heading)
        if repository.get("error"):
            lines.append(f"  {repository['error']}")
            continue
        for series in repository["series"]:
            lines.append(
                f"  {series['label']:<26} {_hours_text(series['median_hours']):>6}  ({series['count']} observed)"
            )
    return "\n".join(lines)


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


def _schedule_line(task: dict) -> str:
    state = "on " if task.get("enabled") else "off"
    nxt = _format_in_zone(task.get("next_run_at"), task.get("timezone"))
    last = task.get("last_status") or "-"
    zone = task.get("timezone") or "-"
    return f"{task['id']}  {state}  {task['schedule']:<15} {zone:<20} next {nxt:<16} last {last:<9} {task['name']}"


def _format_in_zone(iso: str | None, timezone: str | None) -> str:
    """Show an instant as wall-clock time in a task's zone ('-' when unset)."""
    if not iso:
        return "-"
    try:
        moment = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=UTC)
        if timezone:
            moment = moment.astimezone(ZoneInfo(timezone))
    except (ValueError, KeyError):
        return iso[:16].replace("T", " ")
    return moment.strftime("%Y-%m-%d %H:%M")


def _schedule_text(task: dict) -> str:
    lines = [_schedule_line(task), f"  command: {task['command']}"]
    if task.get("cwd"):
        lines.append(f"  cwd: {task['cwd']}")
    return "\n".join(lines)


def _schedule_run_line(run: dict) -> str:
    started = str(run.get("started_at") or "")[:19].replace("T", " ")
    code = "" if run.get("exit_code") is None else f"  exit {run['exit_code']}"
    return f"{started}  {run['status']:<9}{code}  {run['id']}"


def _schedule_run_text(run: dict) -> str:
    line = _schedule_run_line(run)
    if run.get("task_name"):
        line = f"{run['task_name']}  {line}"
    lines = [line]
    if run.get("output"):
        lines.append(run["output"].rstrip())
    return "\n".join(lines)


def _execution_graph_line(graph: dict) -> str:
    state = "on " if graph.get("enabled") else "off"
    schedule = graph.get("schedule") or "-"
    nxt = _format_in_zone(graph.get("next_run_at"), graph.get("timezone"))
    running = "RUNNING" if graph.get("running_execution_id") else "-"
    return f"{graph['id']}  {state}  {schedule:<15} next {nxt:<16} {running:<7} {graph['name']}"


def _execution_graph_text(graph: dict) -> str:
    lines = [_execution_graph_line(graph)]
    if graph.get("description"):
        lines.append(f"  description: {graph['description']}")
    nodes = (graph.get("definition") or {}).get("nodes") or []
    lines.append(f"  nodes: {len(nodes)}, connections: {len((graph.get('definition') or {}).get('edges') or [])}")
    return "\n".join(lines)


def _graph_execution_line(execution: dict) -> str:
    started = str(execution.get("started_at") or "")[:19].replace("T", " ")
    trigger = execution.get("trigger") or "-"
    return f"{started}  {execution['status']:<9} {trigger:<8} {execution['id']}  {execution.get('graph_name', '')}"


def _graph_execution_text(execution: dict) -> str:
    lines = [_graph_execution_line(execution)]
    if execution.get("error"):
        lines.append(f"  error: {execution['error']}")
    if execution.get("task_id"):
        lines.append(f"  task: {execution['task_id']}")
    for node in execution.get("nodes") or []:
        marker = {"done": "*", "failed": "!", "running": ">", "waiting": "?"}.get(node["status"], " ")
        line = f"  {marker} {node['title']}"
        if node.get("run_id"):
            line += f"  (run {node['run_id']})"
        if node.get("error"):
            line += f"  {node['error']}"
        lines.append(line)
        if node.get("output"):
            lines.append("    " + node["output"].strip().replace("\n", "\n    "))
    return "\n".join(lines)


def _operation_line(operation: dict) -> str:
    when = str(operation.get("created_at") or "")[:19]
    return (
        f"{when}  {operation['method']:<6} {operation['status_code']}  "
        f"{operation['client']:<4} {operation['actor']:<5}  {operation['path']}"
    )
