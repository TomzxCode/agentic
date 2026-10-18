"""Coding-agent harnesses, driven over ACP (Agent Client Protocol).

Grouped into harness seeding/resolution, the ACP client, and run execution.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import structlog
from acp import Agent, Client, RequestError
from acp.schema import (
    AllowedOutcome,
    CreateElicitationResponse,
    CreateTerminalResponse,
    DeniedOutcome,
    ElicitationMode,
    KillTerminalResponse,
    PermissionOption,
    ReadTextFileResponse,
    ReleaseTerminalResponse,
    RequestPermissionResponse,
    TerminalOutputResponse,
    WaitForTerminalExitResponse,
    WriteTextFileResponse,
)

log = structlog.get_logger(__name__)


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
