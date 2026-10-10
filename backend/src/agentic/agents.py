"""Coding-agent harnesses, driven over ACP (Agent Client Protocol).

Both OpenCode (`opencode acp`) and pi (via `pi-acp`) speak ACP over stdio, so a
single client here drives any harness. Adding a new harness is a row in the
``harness`` table (or a preset below), not new code.
"""

from __future__ import annotations

import asyncio
import contextlib
import shutil
from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from acp import PROTOCOL_VERSION, Client, RequestError, spawn_agent_process
from acp.schema import (
    AllowedOutcome,
    ClientCapabilities,
    CreateTerminalResponse,
    DeniedOutcome,
    Implementation,
    PermissionOption,
    ReadTextFileResponse,
    RequestPermissionResponse,
    WriteTextFileResponse,
)
from sqlmodel import Session, select

from .config import settings
from .db import engine
from .models import AgentEvent, AgentRun, Harness, RunStatus, utcnow

log = structlog.get_logger(__name__)

HARNESS_PRESETS: list[dict[str, Any]] = [
    {
        "id": "opencode",
        "name": "OpenCode",
        "description": "OpenCode's built-in ACP server (`opencode acp`).",
        "command": "opencode",
        "args": ["acp"],
        "is_default": True,
    },
    {
        "id": "pi",
        "name": "pi",
        "description": "The pi coding agent, via the pi-acp adapter.",
        "command": "pi-acp",
        "args": [],
        "is_default": False,
    },
]


def seed_harnesses(session: Session) -> None:
    if session.exec(select(Harness)).first() is not None:
        return
    for preset in HARNESS_PRESETS:
        session.add(
            Harness(
                id=preset["id"],
                name=preset["name"],
                description=preset["description"],
                command=preset["command"],
                args=preset["args"],
                is_default=preset["is_default"],
            )
        )
    session.commit()


def get_harness(session: Session, harness_id: str | None) -> Harness:
    if harness_id:
        harness = session.get(Harness, harness_id)
        if harness is not None:
            return harness
    harness = session.exec(select(Harness).where(Harness.is_default == True)).first()  # noqa: E712
    if harness is not None:
        return harness
    harness = session.exec(select(Harness).where(Harness.name == settings.default_harness)).first()
    if harness is not None:
        return harness
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

    async def _emit(self, type_: str, text: str, data: dict[str, Any] | None = None) -> None:
        self.seq += 1
        await self._publish({"seq": self.seq, "type": type_, "text": text, "data": data or {}})

    async def session_update(self, session_id: str, update: Any, **kwargs: Any) -> None:
        kind = getattr(update, "session_update", None)
        if kind == "agent_message_chunk":
            await self._emit("message", _content_text(update.content))
        elif kind == "agent_thought_chunk":
            await self._emit("thought", _content_text(update.content))
        elif kind == "user_message_chunk":
            await self._emit("user", _content_text(update.content))
        elif kind == "tool_call":
            await self._emit("tool_call", getattr(update, "title", ""), _dump(update))
        elif kind == "tool_call_update":
            await self._emit("tool_update", getattr(update, "title", "") or "", _dump(update))
        elif kind == "plan":
            entries = [_dump(e) for e in getattr(update, "entries", [])]
            await self._emit("plan", "", {"entries": entries})
        elif kind == "usage_update":
            await self._emit("usage", "", _dump(update))
        else:
            await self._emit("info", kind or "update", _dump(update))

    async def request_permission(
        self, session_id: str, tool_call: Any, options: list[PermissionOption], **kwargs: Any
    ) -> RequestPermissionResponse:
        await self._emit(
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

    async def ext_method(self, method: str, **kwargs: Any) -> dict[str, Any]:
        raise RequestError.method_not_found(method)

    async def ext_notification(self, method: str, **kwargs: Any) -> None:
        return None


async def run_agent(
    *,
    run_id: str,
    harness: Harness,
    cwd: str,
    prompt: str,
    publish: EventPublisher,
    cancel_event: asyncio.Event,
) -> dict[str, Any]:
    """Spawn a harness, run one prompt, stream updates through ``publish``.

    Returns a summary dict (``session_id``, ``stop_reason``).
    """
    env = {**harness.env} if harness.env else None
    args = list(harness.args or [])
    if harness.model:
        # Both opencode and pi accept --model; harmless if ignored.
        args += ["--model", harness.model]

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
        session = await conn.new_session(cwd=cwd)
        session_id = session.session_id
        result["session_id"] = session_id

        cancel_task = asyncio.create_task(cancel_event.wait())
        prompt_task = asyncio.create_task(conn.prompt(session_id, [{"type": "text", "text": prompt}]))
        try:
            done, _pending = await asyncio.wait({prompt_task, cancel_task}, return_when=asyncio.FIRST_COMPLETED)
            if cancel_task in done and not prompt_task.done():
                with contextlib.suppress(Exception):
                    await conn.cancel(session_id)
                with contextlib.suppress(Exception):
                    await prompt_task
                result["stop_reason"] = "cancelled"
            else:
                response = prompt_task.result()
                result["stop_reason"] = getattr(response, "stop_reason", None)
                usage = getattr(response, "usage", None)
                if usage is not None:
                    await publish({"seq": client.seq + 1, "type": "usage", "text": "", "data": _dump(usage)})
        finally:
            cancel_task.cancel()
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

    with Session(engine) as session:
        run = session.get(AgentRun, run_id)
        if run is None:
            return
        run.status = RunStatus.running
        run.started_at = utcnow()
        session.add(run)
        session.commit()
        problem_id = run.problem_id
        harness = get_harness(session, harness_id)

    async def publish(event: dict[str, Any]) -> None:
        with Session(engine) as s:
            persist_event(s, run_id, event)
        await bus.publish(f"run:{run_id}", event)
        await bus.publish(f"problem:{problem_id}", {"kind": "run", "run_id": run_id, **event})

    try:
        summary = await run_agent(
            run_id=run_id, harness=harness, cwd=cwd, prompt=prompt, publish=publish, cancel_event=cancel_event
        )
        with Session(engine) as s:
            run = s.get(AgentRun, run_id)
            if run is not None:
                run.session_id = summary.get("session_id")
                run.stop_reason = str(summary.get("stop_reason") or "")
                run.status = RunStatus.cancelled if summary.get("stop_reason") == "cancelled" else RunStatus.succeeded
                run.ended_at = utcnow()
                s.add(run)
                s.commit()
    except Exception as exc:  # noqa: BLE001
        log.warning("agent run failed", run_id=run_id, error=str(exc))
        with Session(engine) as s:
            run = s.get(AgentRun, run_id)
            if run is not None:
                run.status = RunStatus.failed
                run.error = str(exc)
                run.ended_at = utcnow()
                s.add(run)
                s.commit()
        await publish({"seq": 10_000, "type": "error", "text": f"{type(exc).__name__}: {exc}", "data": {}})
    finally:
        await bus.publish(f"run:{run_id}", {"type": "run_finished", "text": "", "data": {"run_id": run_id}})


async def execute_context_refresh(
    *,
    run_id: str,
    problem_id: str,
    harness_id: str | None,
    cwd: str,
    prompt: str,
    cancel_event: asyncio.Event,
    problem_ctx: dict[str, Any] | None = None,
) -> None:
    """Run a context-refresh turn, then store the parsed summary and next steps."""
    from .crud import add_timeline
    from .events import bus
    from .models import Problem
    from .services import extract_context_json

    await execute_run(run_id=run_id, harness_id=harness_id, cwd=cwd, prompt=prompt, cancel_event=cancel_event)

    with Session(engine) as session:
        events = session.exec(select(AgentEvent).where(AgentEvent.run_id == run_id).order_by(AgentEvent.seq)).all()
        # Prefer the agent's answer; only fall back to thoughts if it said nothing.
        text = "".join(e.text for e in events if e.type == "message")
        if not text.strip():
            text = "".join(e.text for e in events if e.type == "thought")
        data = extract_context_json(text)
        problem = session.get(Problem, problem_id)
        if data and problem is not None:
            problem.summary = data.get("summary", problem.summary)
            problem.next_steps = data.get("next_steps", problem.next_steps)
            problem.context_updated_at = utcnow()
            session.add(problem)
            session.commit()
            add_timeline(session, problem_id, "context_updated", "Context and next steps refreshed", {"run_id": run_id})
        else:
            add_timeline(
                session,
                problem_id,
                "context_refresh_failed",
                "Could not parse context from the agent reply",
                {"run_id": run_id},
            )
    await bus.publish(f"problem:{problem_id}", {"kind": "problem", "action": "context_updated", "run_id": run_id})
