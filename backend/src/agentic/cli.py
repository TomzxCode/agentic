"""Agentic CLI.

A thin, scriptable client over the Agentic HTTP API, meant to be driven by
people and by agents. Commands return data; use ``--format json`` (or pipe the
output, which selects json automatically) for machine-readable results.

    agentic problem create --title "Fix flaky tests"
    agentic link add <problem> --source github --url https://github.com/o/r/issues/1
    agentic worktree create <problem>
    agentic context refresh <problem>
    agentic run create <problem> --prompt "Investigate the failure"
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
}

ProblemStatus = Literal["open", "in_progress", "blocked", "done", "archived"]
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
    return AgenticClient(CONTEXT["api_url"], timeout=CONTEXT["timeout"])


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


def _problem_line(problem: dict) -> str:
    return f"{problem['id']}  [{problem['status']}] p{problem['priority']}  {problem['title']}"


def _problem_text(problem: dict) -> str:
    lines = [_problem_line(problem)]
    if problem.get("summary"):
        lines.append(f"  summary: {problem['summary']}")
    for step in problem.get("next_steps") or []:
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


# --- app ------------------------------------------------------------------
# Plain console: no Rich markup (so `[open]` stays literal) and no wrapping
# (so json output stays valid when piped).
_CONSOLE = Console(markup=False, highlight=False, soft_wrap=True)

app = App(
    name="agentic",
    help="Drive the Agentic app (problems, items, agents) from the command line.",
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


# --- serve ----------------------------------------------------------------
@app.command(name="serve")
def serve(host: str = "127.0.0.1", port: int = 8600, reload: bool = False) -> None:
    """Run the Agentic API server (and serve the built SPA if present)."""
    import uvicorn

    uvicorn.run("agentic.main:app", host=host, port=port, reload=reload)


@app.command(name="health")
@safe
def health() -> str:
    """Check that the API is reachable."""
    with _client() as client:
        data = client.health()
    return emit(data, f"{data.get('status')} ({data.get('service')}) at {CONTEXT['api_url']}")


# --- problems -------------------------------------------------------------
problem_app = App(name="problem", help="Create and manage problems.")
app.command(problem_app)


@problem_app.command(name="list")
@safe
def problem_list(status: ProblemStatus | None = None, q: str | None = None) -> str:
    """List problems, newest first."""
    with _client() as client:
        problems = client.list_problems(status=status, q=q)
    return emit(problems, _join(problems, _problem_line))


@problem_app.command(name="get")
@safe
def problem_get(problem_id: str) -> str:
    """Show a problem with its items, worktrees, runs, and timeline."""
    with _client() as client:
        problem = client.get_problem(problem_id)
    return emit(problem, _problem_text(problem))


@problem_app.command(name="create")
@safe
def problem_create(
    title: str,
    description: str = "",
    priority: int = 2,
    status: ProblemStatus = "open",
    tags: list[str] | None = None,
    repository_id: str | None = None,
    harness_id: str | None = None,
) -> str:
    """Create a problem."""
    with _client() as client:
        problem = client.create_problem(
            title=title,
            description=description,
            priority=priority,
            status=status,
            tags=tags,
            repository_id=repository_id,
            harness_id=harness_id,
        )
    return emit(problem, f"created {problem['id']}  {problem['title']}")


@problem_app.command(name="update")
@safe
def problem_update(
    problem_id: str,
    title: str | None = None,
    description: str | None = None,
    status: ProblemStatus | None = None,
    priority: int | None = None,
    tags: list[str] | None = None,
    repository_id: str | None = None,
    harness_id: str | None = None,
    summary: str | None = None,
) -> str:
    """Update a problem's fields."""
    with _client() as client:
        problem = client.update_problem(
            problem_id,
            title=title,
            description=description,
            status=status,
            priority=priority,
            tags=tags,
            repository_id=repository_id,
            harness_id=harness_id,
            summary=summary,
        )
    return emit(problem, f"updated {problem['id']}  {_problem_line(problem)}")


@problem_app.command(name="delete")
@safe
def problem_delete(problem_id: str) -> str:
    """Delete a problem and everything attached to it."""
    with _client() as client:
        client.delete_problem(problem_id)
    return emit({"deleted": problem_id}, f"deleted {problem_id}")


@problem_app.command(name="timeline")
@safe
def problem_timeline(problem_id: str) -> str:
    """Show a problem's timeline."""
    with _client() as client:
        events = client.problem_timeline(problem_id)
    text = _join(events, lambda e: f"{e['created_at'][:19]}  {e['type']:<18} {e['message']}")
    return emit(events, text)


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
    source: Source,
    url: str | None = None,
    title: str = "",
    content: str = "",
    external_id: str | None = None,
    fetch: bool = True,
) -> str:
    """Create an item (fetches metadata/content unless --no-fetch)."""
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


@item_app.command(name="delete")
@safe
def item_delete(item_id: str) -> str:
    """Delete an item and its associations."""
    with _client() as client:
        client.delete_item(item_id)
    return emit({"deleted": item_id}, f"deleted {item_id}")


# --- links ----------------------------------------------------------------
link_app = App(name="link", help="Associate items with problems.")
app.command(link_app)


@link_app.command(name="add")
@safe
def link_add(
    problem_id: str,
    item_id: str | None = None,
    source: Source | None = None,
    url: str | None = None,
    title: str = "",
    content: str = "",
    external_id: str | None = None,
    note: str = "",
    fetch: bool = True,
) -> str:
    """Associate an existing item (--item-id) or a new one (--source) with a problem."""
    item = None
    if item_id is None:
        if source is None:
            print("error: provide --item-id or --source", file=sys.stderr)
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
        association = client.associate(problem_id, item_id=item_id, item=item, note=note)
    return emit(association, f"linked {association['item']['id']} to {problem_id}")


@link_app.command(name="remove")
@safe
def link_remove(problem_id: str, item_id: str) -> str:
    """Remove an item's association with a problem."""
    with _client() as client:
        client.unassociate(problem_id, item_id)
    return emit({"unlinked": item_id}, f"unlinked {item_id} from {problem_id}")


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
worktree_app = App(name="worktree", help="Create isolated git worktrees for problems.")
app.command(worktree_app)


@worktree_app.command(name="list")
@safe
def worktree_list(problem_id: str) -> str:
    """List a problem's worktrees."""
    with _client() as client:
        worktrees = client.list_worktrees(problem_id)
    return emit(worktrees, _join(worktrees, lambda w: f"{w['id']}  [{w['status']}] {w['branch']}  {w['path']}"))


@worktree_app.command(name="create")
@safe
def worktree_create(
    problem_id: str,
    repository_id: str | None = None,
    branch: str | None = None,
    base: str | None = None,
) -> str:
    """Create a worktree for a problem."""
    with _client() as client:
        worktree = client.create_worktree(problem_id, repository_id=repository_id, branch=branch, base=base)
    return emit(worktree, f"created worktree {worktree['id']}  {worktree['branch']}  {worktree['path']}")


@worktree_app.command(name="remove")
@safe
def worktree_remove(problem_id: str, worktree_id: str) -> str:
    """Remove a worktree from disk and stop tracking it."""
    with _client() as client:
        client.remove_worktree(problem_id, worktree_id)
    return emit({"removed": worktree_id}, f"removed worktree {worktree_id}")


# --- runs -----------------------------------------------------------------
run_app = App(name="run", help="Start, watch, and inspect agent runs.")
app.command(run_app)


@run_app.command(name="list")
@safe
def run_list(problem_id: str) -> str:
    """List a problem's agent runs."""
    with _client() as client:
        runs = client.list_runs(problem_id)
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
    problem_id: str,
    prompt: str,
    harness_id: str | None = None,
    worktree_id: str | None = None,
    cwd: str | None = None,
) -> str:
    """Start an agent run against a problem."""
    with _client() as client:
        run = client.create_run(problem_id, prompt, harness_id=harness_id, worktree_id=worktree_id, cwd=cwd)
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


# --- context --------------------------------------------------------------
context_app = App(name="context", help="Read or refresh a problem's agent-maintained context.")
app.command(context_app)


@context_app.command(name="get")
@safe
def context_get(problem_id: str) -> str:
    """Show a problem's current summary and next steps."""
    with _client() as client:
        context = client.get_context(problem_id)
    text = context.get("summary", "")
    for step in context.get("next_steps") or []:
        text += f"\n- [{'x' if step.get('done') else ' '}] {step.get('text')}"
    return emit(context, text or "(no context yet)")


@context_app.command(name="refresh")
@safe
def context_refresh(problem_id: str) -> str:
    """Ask an agent to rewrite the summary and next steps."""
    with _client() as client:
        run = client.refresh_context(problem_id)
    return emit(run, f"context refresh started: run {run['id']}")


# --- harnesses ------------------------------------------------------------
harness_app = App(name="harness", help="Inspect and configure agent harnesses.")
app.command(harness_app)


@harness_app.command(name="list")
@safe
def harness_list() -> str:
    """List harnesses and whether they are on PATH."""
    with _client() as client:
        harnesses = client.list_harnesses()
    text = _join(
        harnesses, lambda h: f"{h['id']:<10} {'available' if h['available'] else 'missing':<10} {h.get('detail', '')}"
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


@settings_app.command(name="set")
@safe
def settings_set(
    openchamber_url: str | None = None,
    openchamber_session_path: str | None = None,
    terminal_url_template: str | None = None,
) -> str:
    """Override session-link settings (empty string disables a link)."""
    with _client() as client:
        settings = client.update_settings(
            openchamber_url=openchamber_url,
            openchamber_session_path=openchamber_session_path,
            terminal_url_template=terminal_url_template,
        )
    effective = settings["effective"]
    text = "\n".join(f"{key} = {value!r}" for key, value in effective.items())
    return emit(settings, text)


def main() -> None:
    app.meta()


if __name__ == "__main__":
    main()
