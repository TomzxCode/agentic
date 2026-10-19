"""CLI commands."""

from __future__ import annotations

import json
import time

from cyclopts import App

from .. import runtime
from ..render import (
    _join,
    _run_line,
    _run_text,
    _session_line,
    _session_text,
)
from ..runtime import (
    _resolve_format,
    emit,
    safe,
)

run_app = App(name="run", help="Start, watch, and inspect agent runs.")
session_app = App(name="session", help="Record agent sessions against tasks and reopen them.")
context_app = App(name="context", help="Read or refresh a task's agent-maintained context.")


def register(app: App) -> None:
    app.command(run_app)
    app.command(session_app)
    app.command(context_app)


@run_app.command(name="list")
@safe
def run_list(task_id: str) -> str:
    """List a task's agent runs."""
    with runtime._client() as client:
        runs = client.list_runs(task_id)
    return emit(runs, _join(runs, _run_line))


@run_app.command(name="get")
@safe
def run_get(run_id: str) -> str:
    """Show a run, including its session links."""
    with runtime._client() as client:
        run = client.get_run(run_id)
    return emit(run, _run_text(run))


@run_app.command(name="events")
@safe
def run_events(run_id: str) -> str:
    """Show a run's transcript."""
    with runtime._client() as client:
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
    model: str | None = None,
) -> str:
    """Start an agent run against a task.

    --model selects the model this run answers with, overriding the harness's own
    configured model for this run only; empty means the harness decides.
    """
    with runtime._client() as client:
        run = client.create_run(task_id, prompt, harness_id=harness_id, worktree_id=worktree_id, cwd=cwd, model=model)
    return emit(run, f"started run {run['id']} ({run['status']}) in {run.get('cwd')}")


@run_app.command(name="cancel")
@safe
def run_cancel(run_id: str) -> str:
    """Cancel a running agent."""
    with runtime._client() as client:
        run = client.cancel_run(run_id)
    return emit(run, f"cancelling {run_id}")


@run_app.command(name="wait")
@safe
def run_wait(run_id: str, timeout: float = 600.0, interval: float = 2.0) -> str:
    """Block until a run finishes, then print it."""
    terminal = {"succeeded", "failed", "cancelled"}
    deadline = time.monotonic() + timeout
    with runtime._client() as client:
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
    with runtime._client() as client:
        for event in client.stream_run(run_id):
            if machine:
                print(json.dumps(event, default=str))
            else:
                print(f"[{event.get('type')}] {event.get('text', '')}")
            if event.get("type") == "run_finished":
                break


@session_app.command(name="list")
@safe
def session_list(task_id: str) -> str:
    """List a task's recorded agent sessions."""
    with runtime._client() as client:
        sessions = client.list_sessions(task_id)
    return emit(sessions, _join(sessions, _session_line))


@session_app.command(name="get")
@safe
def session_get(task_id: str, session_id: str) -> str:
    """Show a recorded session and how to reopen it."""
    with runtime._client() as client:
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
    with runtime._client() as client:
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
    with runtime._client() as client:
        session = client.update_session(task_id, session_id, harness_id=harness_id, cwd=cwd, label=label)
    return emit(session, f"updated session {session['id']}  {_session_line(session)}")


@session_app.command(name="remove")
@safe
def session_remove(task_id: str, session_id: str) -> str:
    """Remove a recorded session from a task (the session itself is untouched)."""
    with runtime._client() as client:
        client.delete_session(task_id, session_id)
    return emit({"removed": session_id}, f"removed session {session_id}")


@context_app.command(name="get")
@safe
def context_get(task_id: str) -> str:
    """Show a task's current summary and next steps."""
    with runtime._client() as client:
        context = client.get_context(task_id)
    text = context.get("summary", "")
    for step in context.get("next_steps") or []:
        text += f"\n- [{'x' if step.get('done') else ' '}] {step.get('text')}"
    return emit(context, text or "(no context yet)")


@context_app.command(name="refresh")
@safe
def context_refresh(task_id: str) -> str:
    """Ask an agent to rewrite the summary and next steps."""
    with runtime._client() as client:
        run = client.refresh_context(task_id)
    return emit(run, f"context refresh started: run {run['id']}")
