"""Agent-run execution: the worker entrypoints.

Runs a harness session and persists its transcript, then parses the agent's
reply for a context refresh or a Slack summary. The ACP transport and the
client callbacks live in ``runner`` (and ``client``).
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

import structlog
from sqlmodel import Session, col, select

from ..db import engine
from ..models.agents import AgentEvent, AgentRun
from ..models.base import OperationActor, OperationClient, RunStatus, utcnow
from .harnesses import get_harness
from .runner import persist_event, run_agent

log = structlog.get_logger(__name__)


async def execute_run(
    *,
    run_id: str,
    harness_id: str | None,
    cwd: str,
    prompt: str,
    cancel_event: asyncio.Event,
) -> None:
    """Background entrypoint: run a harness and persist the transcript."""
    from ..events import bus

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
    from ..crud import add_timeline
    from ..events import bus
    from ..models.tasks import Task
    from ..services.prompts import extract_context_json

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
    from ..crud import add_timeline
    from ..events import bus
    from ..models.tasks import Task
    from ..services.prompts import extract_summary_json

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
