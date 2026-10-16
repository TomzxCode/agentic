"""Coding-agent harnesses, driven over ACP (Agent Client Protocol).

OpenCode (`opencode acp`, v1 or v2), pi (via `pi-acp`), and any other ACP agent
speak the protocol over stdio, so a single client here drives any harness.
Adding a new harness is a row in the ``harness`` table (or a preset below), not
new code.
"""

from __future__ import annotations

import asyncio
import contextlib
import shutil
from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from acp import PROTOCOL_VERSION, Agent, Client, RequestError, spawn_agent_process
from acp.schema import (
    AllowedOutcome,
    ClientCapabilities,
    CreateElicitationResponse,
    CreateTerminalResponse,
    DeniedOutcome,
    ElicitationMode,
    Implementation,
    KillTerminalResponse,
    PermissionOption,
    ReadTextFileResponse,
    ReleaseTerminalResponse,
    RequestPermissionResponse,
    TerminalOutputResponse,
    TextContentBlock,
    WaitForTerminalExitResponse,
    WriteTextFileResponse,
)
from sqlmodel import Session, col, select

from .config import settings
from .db import engine
from .models import AgentEvent, AgentRun, Harness, OperationActor, OperationClient, RunStatus, Setting, utcnow

log = structlog.get_logger(__name__)

HARNESS_PRESETS: list[dict[str, Any]] = [
    {
        "id": "opencode",
        "name": "OpenCode",
        "description": "OpenCode's built-in ACP server (`opencode acp`).",
        "command": "opencode",
        "args": ["acp"],
        "resume_command": "opencode --session {session}",
    },
    {
        "id": "opencode2",
        "name": "OpenCode v2",
        "description": "OpenCode v2's built-in ACP server (`opencode2 acp`).",
        "command": "opencode2",
        "args": ["acp"],
        "resume_command": "opencode2 --session {session}",
    },
    {
        "id": "pi",
        "name": "pi",
        "description": "The pi coding agent, via the pi-acp adapter.",
        "command": "pi-acp",
        "args": [],
        "resume_command": "pi --session {session}",
    },
]

RESUME_DEFAULTS = {
    "opencode": "opencode --session {session}",
    "opencode2": "opencode2 --session {session}",
    "pi": "pi --session {session}",
}

# OpenCode v2 is seeded as the default when its binary is installed. The seeded
# choice is recorded once, so a default later chosen in Settings always wins.
OPENCODE_DEFAULT_PREFERENCE = ("opencode2", "opencode")
OPENCODE_DEFAULT_MARKER = "harness_default_seeded"


def _preferred_opencode_default() -> str:
    for harness_id in OPENCODE_DEFAULT_PREFERENCE:
        if shutil.which(harness_id):
            return harness_id
    return OPENCODE_DEFAULT_PREFERENCE[-1]


def seed_harnesses(session: Session) -> None:
    """Create the built-in harness presets, pick a default, and backfill fields.

    Missing presets are inserted on every call, so upgrading adds new built-ins
    (for example ``opencode2``) to an existing database. Existing rows are never
    overwritten, so custom edits survive.
    """
    existing = {harness.id for harness in session.exec(select(Harness)).all()}
    changed = False
    for preset in HARNESS_PRESETS:
        if preset["id"] in existing:
            continue
        session.add(
            Harness(
                id=preset["id"],
                name=preset["name"],
                description=preset["description"],
                command=preset["command"],
                args=preset["args"],
                resume_command=preset.get("resume_command"),
                is_default=False,
            )
        )
        changed = True
    if changed:
        session.commit()
    _ensure_default_harness(session)
    # Backfill resume commands for harnesses created before the column existed.
    changed = False
    for harness in session.exec(select(Harness)).all():
        if not harness.resume_command:
            fallback = RESUME_DEFAULTS.get(harness.id) or RESUME_DEFAULTS.get(harness.name.lower())
            if fallback:
                harness.resume_command = fallback
                session.add(harness)
                changed = True
    if changed:
        session.commit()


def _ensure_default_harness(session: Session) -> None:
    """Guarantee a single default harness, preferring installed OpenCode v2.

    Seeding picks the default once, and only while no default is set or the set
    one is an OpenCode variant, so a deliberate choice (including one made in
    Settings) is never overwritten.
    """
    current = session.exec(select(Harness).where(Harness.is_default == True)).first()  # noqa: E712
    if session.get(Setting, OPENCODE_DEFAULT_MARKER) is not None and current is not None:
        return
    if current is not None and current.id not in OPENCODE_DEFAULT_PREFERENCE:
        _mark_default_seeded(session)
        session.commit()
        return
    target = session.get(Harness, _preferred_opencode_default()) or session.exec(select(Harness)).first()
    if target is None:
        return
    for harness in session.exec(select(Harness)).all():
        want = harness.id == target.id
        if harness.is_default != want:
            harness.is_default = want
            session.add(harness)
    _mark_default_seeded(session)
    session.commit()


def _mark_default_seeded(session: Session) -> None:
    if session.get(Setting, OPENCODE_DEFAULT_MARKER) is None:
        session.add(Setting(key=OPENCODE_DEFAULT_MARKER, value="1"))


def get_harness(session: Session, harness_id: str | None) -> Harness:
    if harness_id:
        harness = session.get(Harness, harness_id)
        if harness is not None:
            return harness
    harness = session.exec(select(Harness).where(Harness.is_default == True)).first()  # noqa: E712
    if harness is None:
        harness = session.exec(select(Harness).where(Harness.name == settings.default_harness)).first()
    if harness is None:
        harness = session.exec(select(Harness)).first()
    if harness is None:
        raise RuntimeError("No harness configured")
    return harness


def harness_available(harness: Harness) -> tuple[bool, str]:
    path = shutil.which(harness.command)
    if not path:
        return False, f"`{harness.command}` not found on PATH"
    return True, path


def _content_text(content: Any) -> str:
    kind = getattr(content, "type", None)
    if kind == "text":
        return content.text
    if kind == "image":
        return "[image]"
    if kind == "audio":
        return "[audio]"
    if kind == "resource_link":
        return f"[{getattr(content, 'name', 'resource')}]({getattr(content, 'uri', '')})"
    if kind == "resource":
        resource = getattr(content, "resource", None)
        return getattr(resource, "text", None) or f"[resource {getattr(resource, 'uri', '')}]"
    return ""


def _dump(model: Any) -> dict[str, Any]:
    if model is None:
        return {}
    try:
        return model.model_dump(by_alias=True, mode="json", exclude_none=True)
    except Exception:  # pragma: no cover - defensive
        return {"repr": repr(model)}


EventPublisher = Callable[[dict[str, Any]], Awaitable[None]]


class AgenticClient(Client):
    """ACP client callbacks. Normalizes updates and forwards them to a publisher."""

    def __init__(self, cwd: str, publish: EventPublisher, auto_approve: bool = True) -> None:
        self.cwd = cwd
        self._publish = publish
        self._auto_approve = auto_approve
        self.seq = 0

    async def emit(self, type_: str, text: str, data: dict[str, Any] | None = None) -> None:
        self.seq += 1
        await self._publish({"seq": self.seq, "type": type_, "text": text, "data": data or {}})

    async def session_update(self, session_id: str, update: Any, **kwargs: Any) -> None:
        kind = getattr(update, "session_update", None)
        if kind == "agent_message_chunk":
            await self.emit("message", _content_text(update.content))
        elif kind == "agent_thought_chunk":
            await self.emit("thought", _content_text(update.content))
        elif kind == "user_message_chunk":
            await self.emit("user", _content_text(update.content))
        elif kind == "tool_call":
            await self.emit("tool_call", getattr(update, "title", ""), _dump(update))
        elif kind == "tool_call_update":
            await self.emit("tool_update", getattr(update, "title", "") or "", _dump(update))
        elif kind == "plan":
            entries = [_dump(e) for e in getattr(update, "entries", [])]
            await self.emit("plan", "", {"entries": entries})
        elif kind == "usage_update":
            await self.emit("usage", "", _dump(update))
        else:
            await self.emit("info", kind or "update", _dump(update))

    async def request_permission(
        self, session_id: str, tool_call: Any, options: list[PermissionOption], **kwargs: Any
    ) -> RequestPermissionResponse:
        await self.emit(
            "permission",
            f"Permission requested for {getattr(tool_call, 'title', 'a tool')}",
            {"options": [_dump(o) for o in options]},
        )
        if self._auto_approve and options:
            chosen = next((o for o in options if o.kind == "allow_once"), None) or next(
                (o for o in options if str(o.kind).startswith("allow")), options[0]
            )
            return RequestPermissionResponse(
                outcome=AllowedOutcome.model_validate({"outcome": "selected", "optionId": chosen.option_id})
            )
        return RequestPermissionResponse(outcome=DeniedOutcome(outcome="cancelled"))

    async def read_text_file(
        self, session_id: str, path: str, line: int | None = None, limit: int | None = None, **kwargs: Any
    ) -> ReadTextFileResponse:
        from pathlib import Path

        target = Path(path)
        if not target.is_absolute():
            target = Path(self.cwd) / target
        text = target.read_text(errors="replace")
        if line is not None or limit is not None:
            lines = text.splitlines(keepends=True)
            start = (line - 1) if line else 0
            text = "".join(lines[start : start + limit] if limit else lines[start:])
        return ReadTextFileResponse(content=text)

    async def write_text_file(
        self, session_id: str, path: str, content: str, **kwargs: Any
    ) -> WriteTextFileResponse | None:
        from pathlib import Path

        target = Path(path)
        if not target.is_absolute():
            target = Path(self.cwd) / target
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        return WriteTextFileResponse()

    async def create_terminal(
        self,
        session_id: str,
        command: str,
        args: list[str] | None = None,
        env: Any = None,
        cwd: str | None = None,
        output_byte_limit: int | None = None,
        **kwargs: Any,
    ) -> CreateTerminalResponse:
        # Terminal execution is not offered; agents use their own tools.
        raise RequestError.method_not_found("terminal/create")

    async def terminal_output(self, session_id: str, terminal_id: str, **kwargs: Any) -> TerminalOutputResponse:
        raise RequestError.method_not_found("terminal/output")

    async def release_terminal(
        self, session_id: str, terminal_id: str, **kwargs: Any
    ) -> ReleaseTerminalResponse | None:
        raise RequestError.method_not_found("terminal/release")

    async def wait_for_terminal_exit(
        self, session_id: str, terminal_id: str, **kwargs: Any
    ) -> WaitForTerminalExitResponse:
        raise RequestError.method_not_found("terminal/wait_for_exit")

    async def kill_terminal(self, session_id: str, terminal_id: str, **kwargs: Any) -> KillTerminalResponse | None:
        raise RequestError.method_not_found("terminal/kill")

    async def create_elicitation(self, message: str, mode: ElicitationMode, **kwargs: Any) -> CreateElicitationResponse:
        raise RequestError.method_not_found("elicitation/create")

    async def complete_elicitation(self, elicitation_id: str, **kwargs: Any) -> None:
        return None

    def on_connect(self, conn: Agent) -> None:
        return None

    async def ext_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        raise RequestError.method_not_found(method)

    async def ext_notification(self, method: str, params: dict[str, Any]) -> None:
        return None


async def _acquire_session(conn: Any, cwd: str, resume_session_id: str | None) -> tuple[str, str | None]:
    """Resume an existing session when asked, else open a new one.

    Resuming keeps the conversation context, so a retried run continues where the
    previous attempt stopped instead of starting over. Returns the session id and
    the model the harness reports for that session, so a run can say what
    answered even when it selects no model of its own.
    """
    if resume_session_id:
        try:
            resumed = await conn.resume_session(session_id=resume_session_id, cwd=cwd)
            return resume_session_id, _session_model(resumed)
        except Exception as exc:  # noqa: BLE001 - a missing session is recoverable
            log.info("could not resume session; starting a new one", session_id=resume_session_id, error=str(exc))
    session = await conn.new_session(cwd=cwd)
    return session.session_id, _session_model(session)


def _session_model(response: Any) -> str | None:
    """The model an ACP session response reports, or None when it reports none.

    ACP carries the session's model as a config option whose ``currentValue`` is
    the model in use. The option's id is ``model``; its ``category`` says the
    same when a harness picks another id. A harness with no such option says
    nothing, and the run then has no model to print rather than a guess.
    """
    options = getattr(response, "config_options", None) or []
    for option in options:
        value = getattr(option, "current_value", None)
        if value is None:
            continue
        if getattr(option, "id", None) == "model" or getattr(option, "category", None) == "model":
            return str(value)
    return None


async def _apply_model(conn: Any, session_id: str, model: str | None) -> tuple[str | None, str | None]:
    """Select the session model over ACP.

    The model is chosen with the ACP ``session/set_config_option`` request (the
    ``model`` config option), not a command-line flag: ``opencode acp`` rejects
    ``--model`` as an unknown flag and would fail to start. A harness that does
    not expose a model option, or rejects the requested value, keeps its own
    default; the caller surfaces the returned message instead of failing the run.

    Returns the model the session reports afterwards (the requested one when the
    response does not say, which is also what a harness that ignores the request
    keeps claiming) and the error message, if any.
    """
    if not model:
        return None, None
    try:
        response = await conn.set_config_option(config_id="model", session_id=session_id, value=model)
    except Exception as exc:  # noqa: BLE001 - an unsupported option must not fail the run
        log.warning("could not select harness model", model=model, error=str(exc))
        return None, str(exc)
    return _session_model(response) or model, None


def harness_env(harness: Harness) -> dict[str, str]:
    """The environment for a harness process, marking it as an agent.

    The ACP transport merges this over the default environment. Setting
    ``AGENTIC_ACTOR=agent`` means any ``agentic`` CLI call the harness makes is
    attributed to an agent rather than a person.
    """
    return {**(harness.env or {}), "AGENTIC_ACTOR": "agent"}


async def run_agent(
    *,
    run_id: str,
    harness: Harness,
    cwd: str,
    prompt: str,
    publish: EventPublisher,
    cancel_event: asyncio.Event,
    resume_session_id: str | None = None,
    on_session: Callable[[str], Awaitable[None]] | None = None,
) -> dict[str, Any]:
    """Spawn a harness, run one prompt, stream updates through ``publish``.

    ``on_session`` is called with the session id as soon as it exists (created or
    resumed), so the caller can persist it before the turn finishes. A
    ``resume_session_id`` continues an existing session rather than starting a new
    one. Returns a summary dict (``session_id``, ``stop_reason``), plus ``model``
    when the harness names the model the session answers with.
    """
    env = harness_env(harness)
    args = list(harness.args or [])

    client = AgenticClient(cwd=cwd, publish=publish, auto_approve=settings.auto_approve_permissions)
    result: dict[str, Any] = {}

    async with spawn_agent_process(client, harness.command, *args, env=env, cwd=cwd) as (conn, process):
        init = await conn.initialize(
            protocol_version=PROTOCOL_VERSION,
            client_capabilities=ClientCapabilities(
                terminal=False,
                fs={"readTextFile": True, "writeTextFile": True},
            ),
            client_info=Implementation(name="agentic", title="Agentic", version="0.1.0"),
        )
        result["agent_info"] = _dump(getattr(init, "agent_info", None) or getattr(init, "agentInfo", None))
        session_id, session_model = await _acquire_session(conn, cwd, resume_session_id)
        result["session_id"] = session_id
        if on_session is not None:
            # Persist the handle before the turn runs, so a crash leaves a resumable run.
            await on_session(session_id)
        selected_model, model_error = await _apply_model(conn, session_id, harness.model)
        if model_error is not None:
            await client.emit("warning", f"Could not select model {harness.model}: {model_error}")
        # What the session answers with: the model the harness reported after the
        # selection, else the one it reported for the session, else the harness's
        # own configured model. The transcript header and the run row read this,
        # so a live run names its model before its first token.
        model = selected_model or session_model or harness.model
        if model:
            result["model"] = model
            await client.emit("model", model)

        cancel_task = asyncio.create_task(cancel_event.wait())
        prompt_task = asyncio.create_task(conn.prompt(session_id, [TextContentBlock(type="text", text=prompt)]))
        # Watch the harness process too: if it exits before answering, the prompt
        # never resolves and the run would stay "running" forever.
        exit_task = asyncio.create_task(process.wait())
        try:
            done, _pending = await asyncio.wait(
                {prompt_task, cancel_task, exit_task}, return_when=asyncio.FIRST_COMPLETED
            )
            if prompt_task in done:
                response = prompt_task.result()
                result["stop_reason"] = getattr(response, "stop_reason", None)
                usage = getattr(response, "usage", None)
                if usage is not None:
                    await publish({"seq": client.seq + 1, "type": "usage", "text": "", "data": _dump(usage)})
            elif cancel_task in done:
                with contextlib.suppress(Exception):
                    await conn.cancel(session_id)
                with contextlib.suppress(Exception):
                    await prompt_task
                result["stop_reason"] = "cancelled"
            else:
                code = exit_task.result()
                raise RuntimeError(f"agent process exited (code {code}) before completing the prompt")
        finally:
            for task in (cancel_task, exit_task):
                task.cancel()
            if process.returncode is None:
                with contextlib.suppress(ProcessLookupError):
                    process.terminate()
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(process.wait(), timeout=10)

    return result


def persist_event(session: Session, run_id: str, event: dict[str, Any]) -> AgentEvent:
    row = AgentEvent(
        run_id=run_id,
        seq=event.get("seq", 0),
        type=event.get("type", "info"),
        text=event.get("text", ""),
        data_json=event.get("data", {}),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


async def execute_run(
    *,
    run_id: str,
    harness_id: str | None,
    cwd: str,
    prompt: str,
    cancel_event: asyncio.Event,
) -> None:
    """Background entrypoint: run a harness and persist the transcript."""
    from .events import bus

    task_id: str | None = None

    async def publish(event: dict[str, Any]) -> None:
        try:
            with Session(engine) as s:
                persist_event(s, run_id, event)
        except Exception as exc:  # noqa: BLE001 - a persist hiccup must not kill the run
            log.warning("failed to persist agent event", run_id=run_id, error=str(exc))
        await bus.publish(f"run:{run_id}", event)
        if task_id:
            await bus.publish(f"task:{task_id}", {"kind": "run", "run_id": run_id, **event})

    async def record_session(session_id: str) -> None:
        # Persist the session handle as soon as it exists, so an interrupted run
        # can be resumed instead of starting over.
        with Session(engine) as s:
            row = s.get(AgentRun, run_id)
            if row is not None:
                row.session_id = session_id
                s.add(row)
                s.commit()
        if task_id:
            await bus.publish(f"task:{task_id}", {"kind": "task", "action": "session_started", "run_id": run_id})

    try:
        with Session(engine) as session:
            run = session.get(AgentRun, run_id)
            if run is None:
                return
            task_id = run.task_id
            # A retry of an interrupted run resumes the harness session it left behind.
            resume_session_id = run.session_id
            run.status = RunStatus.running
            run.started_at = utcnow()
            session.add(run)
            session.commit()
            harness = get_harness(session, harness_id)

        summary = await run_agent(
            run_id=run_id,
            harness=harness,
            cwd=cwd,
            prompt=prompt,
            publish=publish,
            cancel_event=cancel_event,
            resume_session_id=resume_session_id,
            on_session=record_session,
        )
        with Session(engine) as s:
            run = s.get(AgentRun, run_id)
            if run is not None:
                run.session_id = summary.get("session_id")
                # A retried run resumes a session, and a harness that stops
                # reporting its model keeps whatever the first attempt recorded.
                if summary.get("model"):
                    run.model = str(summary["model"])
                run.stop_reason = str(summary.get("stop_reason") or "")
                run.status = RunStatus.cancelled if summary.get("stop_reason") == "cancelled" else RunStatus.succeeded
                run.ended_at = utcnow()
                s.add(run)
                s.commit()
    except Exception as exc:  # noqa: BLE001
        log.warning("agent run failed", run_id=run_id, error=str(exc))
        with contextlib.suppress(Exception), Session(engine) as s:
            run = s.get(AgentRun, run_id)
            if run is not None:
                run.status = RunStatus.failed
                run.error = str(exc)
                run.ended_at = utcnow()
                s.add(run)
                s.commit()
        with contextlib.suppress(Exception):
            await publish({"seq": 10_000, "type": "error", "text": f"{type(exc).__name__}: {exc}", "data": {}})
    finally:
        await bus.publish(f"run:{run_id}", {"type": "run_finished", "text": "", "data": {"run_id": run_id}})
        if task_id:
            await bus.publish(f"task:{task_id}", {"kind": "task", "action": "run_finished", "run_id": run_id})


async def execute_context_refresh(
    *,
    run_id: str,
    task_id: str,
    harness_id: str | None,
    cwd: str,
    prompt: str,
    cancel_event: asyncio.Event,
) -> None:
    """Run a context-refresh turn, then store the parsed summary and next steps."""
    from .crud import add_timeline
    from .events import bus
    from .models import Task
    from .services import extract_context_json

    await execute_run(run_id=run_id, harness_id=harness_id, cwd=cwd, prompt=prompt, cancel_event=cancel_event)

    parsed = False
    with Session(engine) as session:
        events = session.exec(select(AgentEvent).where(AgentEvent.run_id == run_id).order_by(col(AgentEvent.seq))).all()
        # Prefer the agent's answer; only fall back to thoughts if it said nothing.
        text = "".join(e.text for e in events if e.type == "message")
        if not text.strip():
            text = "".join(e.text for e in events if e.type == "thought")
        data = extract_context_json(text)
        task = session.get(Task, task_id)
        if data and task is not None:
            task.summary = data.get("summary", task.summary)
            task.next_steps = data.get("next_steps", task.next_steps)
            task.context_updated_at = utcnow()
            session.add(task)
            session.commit()
            add_timeline(
                session,
                task_id,
                "context_updated",
                "Context and next steps refreshed",
                {"run_id": run_id},
                client=OperationClient.api,
                actor=OperationActor.agent,
            )
            parsed = True
        else:
            add_timeline(
                session,
                task_id,
                "context_refresh_failed",
                "Could not parse context from the agent reply",
                {"run_id": run_id},
                client=OperationClient.api,
                actor=OperationActor.agent,
            )
    await bus.publish(
        f"task:{task_id}",
        {"kind": "task", "action": "context_updated" if parsed else "context_refresh_failed", "run_id": run_id},
    )


async def execute_slack_summary(
    *,
    run_id: str,
    task_id: str,
    harness_id: str | None,
    cwd: str,
    prompt: str,
    cancel_event: asyncio.Event,
    generate_title: bool = True,
) -> None:
    """Delegate an imported Slack thread: store the agent's title and summary.

    A backstop of ``generate_title=False`` keeps a user-supplied title and only
    takes the summary.
    """
    from .crud import add_timeline
    from .events import bus
    from .models import Task
    from .services import extract_summary_json

    await execute_run(run_id=run_id, harness_id=harness_id, cwd=cwd, prompt=prompt, cancel_event=cancel_event)

    parsed = False
    with Session(engine) as session:
        events = session.exec(select(AgentEvent).where(AgentEvent.run_id == run_id).order_by(col(AgentEvent.seq))).all()
        # Prefer the agent's answer; only fall back to thoughts if it said nothing.
        text = "".join(e.text for e in events if e.type == "message")
        if not text.strip():
            text = "".join(e.text for e in events if e.type == "thought")
        data = extract_summary_json(text)
        task = session.get(Task, task_id)
        title = data["title"] if (data and generate_title) else ""
        summary = data["summary"] if data else ""
        if task is not None and (title or summary):
            if title:
                task.title = title
            if summary:
                task.summary = summary
                task.context_updated_at = utcnow()
            task.updated_at = utcnow()
            session.add(task)
            session.commit()
            add_timeline(
                session,
                task_id,
                "summary_updated",
                "Titled and summarized the Slack thread",
                {"run_id": run_id},
                client=OperationClient.api,
                actor=OperationActor.agent,
            )
            parsed = True
        else:
            add_timeline(
                session,
                task_id,
                "summary_failed",
                "Could not parse a title and summary from the agent reply",
                {"run_id": run_id},
                client=OperationClient.api,
                actor=OperationActor.agent,
            )
    await bus.publish(
        f"task:{task_id}",
        {"kind": "task", "action": "summary_updated" if parsed else "summary_failed", "run_id": run_id},
    )
