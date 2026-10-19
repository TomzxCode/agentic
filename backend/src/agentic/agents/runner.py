"""Coding-agent harnesses, driven over ACP (Agent Client Protocol).

Grouped into harness seeding/resolution, the ACP client, and run execution.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from acp import PROTOCOL_VERSION, spawn_agent_process
from acp.schema import (
    ClientCapabilities,
    Implementation,
    TextContentBlock,
)
from sqlmodel import Session

from ..config import settings
from ..models.agents import AgentEvent, Harness
from .client import AgenticClient, EventPublisher, _dump

log = structlog.get_logger(__name__)


async def initialize(conn: Any) -> dict[str, Any]:
    """Hand a harness the client's capabilities and return its agent info."""
    init = await conn.initialize(
        protocol_version=PROTOCOL_VERSION,
        client_capabilities=ClientCapabilities(
            terminal=False,
            fs={"readTextFile": True, "writeTextFile": True},
        ),
        client_info=Implementation(name="agentic", title="Agentic", version="0.1.0"),
    )
    return _dump(getattr(init, "agent_info", None) or getattr(init, "agentInfo", None))


async def _acquire_session(
    conn: Any, cwd: str, resume_session_id: str | None
) -> tuple[str, str | None, list[dict[str, str]]]:
    """Resume an existing session when asked, else open a new one.

    Resuming keeps the conversation context, so a retried run continues where the
    previous attempt stopped instead of starting over. Returns the session id, the
    model the harness reports for that session, and the models the session offers,
    so a run can say what answered (and show the harness's label for it) even when
    it selects no model of its own.
    """
    if resume_session_id:
        try:
            resumed = await conn.resume_session(session_id=resume_session_id, cwd=cwd)
            return resume_session_id, session_model(resumed), session_model_choices(resumed)
        except Exception as exc:  # noqa: BLE001 - a missing session is recoverable
            log.info("could not resume session; starting a new one", session_id=resume_session_id, error=str(exc))
    session = await conn.new_session(cwd=cwd)
    return session.session_id, session_model(session), session_model_choices(session)


def _model_option(response: Any) -> Any | None:
    """The session's model config option, whichever id the harness gives it.

    ACP carries the session's model as a config option whose id is ``model``;
    its ``category`` says the same when a harness picks another id.
    """
    options = getattr(response, "config_options", None) or []
    for option in options:
        if getattr(option, "id", None) == "model" or getattr(option, "category", None) == "model":
            return option
    return None


def session_model(response: Any) -> str | None:
    """The model an ACP session response reports, or None when it reports none.

    A harness with no model option says nothing, and the run then has no model to
    print rather than a guess.
    """
    value = getattr(_model_option(response), "current_value", None)
    return None if value is None else str(value)


def session_model_choices(response: Any) -> list[dict[str, str]]:
    """The models a session response offers for its model option.

    ACP nests the choices under the option's ``options``: a flat list, or grouped
    by provider (the groups are flattened here). An entry is ``{value, name}``,
    the value being the id a run selects and the name the label to show. A
    harness with no model option, or one that reports it as a non-select, offers
    nothing rather than a guess.
    """
    choices: list[dict[str, str]] = []
    for item in getattr(_model_option(response), "options", None) or []:
        nested = getattr(item, "options", None)
        for entry in nested if nested is not None else [item]:
            value = getattr(entry, "value", None)
            if value is None:
                continue
            choices.append({"value": str(value), "name": str(getattr(entry, "name", None) or value)})
    return choices


def model_name(choices: list[dict[str, str]], model: str | None) -> str | None:
    """The label a harness gives a model id, or None when it does not name it."""
    if not model:
        return None
    for choice in choices:
        if choice["value"] == model:
            return choice["name"]
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
    return session_model(response) or model, None


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
    model_override: str | None = None,
    on_session: Callable[[str], Awaitable[None]] | None = None,
) -> dict[str, Any]:
    """Spawn a harness, run one prompt, stream updates through ``publish``.

    ``on_session`` is called with the session id as soon as it exists (created or
    resumed), so the caller can persist it before the turn finishes. A
    ``resume_session_id`` continues an existing session rather than starting a new
    one. ``model_override`` selects the session model for this run, taking
    precedence over the harness's own configured model. Returns a summary dict
    (``session_id``, ``stop_reason``), plus ``model`` when the harness names the
    model the session answers with.
    """
    env = harness_env(harness)
    args = list(harness.args or [])

    client = AgenticClient(cwd=cwd, publish=publish, auto_approve=settings.auto_approve_permissions)
    result: dict[str, Any] = {}

    async with spawn_agent_process(client, harness.command, *args, env=env, cwd=cwd) as (conn, process):
        result["agent_info"] = await initialize(conn)
        session_id, reported_model, session_choices = await _acquire_session(conn, cwd, resume_session_id)
        result["session_id"] = session_id
        if on_session is not None:
            # Persist the handle before the turn runs, so a crash leaves a resumable run.
            await on_session(session_id)
        requested_model = model_override or harness.model
        selected_model, model_error = await _apply_model(conn, session_id, requested_model)
        if model_error is not None:
            await client.emit("warning", f"Could not select model {requested_model}: {model_error}")
        # What the session answers with: the model the harness reported after the
        # selection, else the one it reported for the session, else the model the
        # run asked for. The transcript header and the run row read this, so a
        # live run names its model before its first token.
        model = selected_model or reported_model or requested_model
        if model:
            result["model"] = model
            # The harness's own label for that model, so a run reads as "GLM 5.3"
            # rather than the id it selects with. A harness that names nothing
            # leaves the run's model as the id.
            label = model_name(session_choices, model)
            if label:
                result["model_name"] = label
            await client.emit("model", label or model)

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
