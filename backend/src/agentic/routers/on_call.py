"""On-call view: scan a Slack channel and prepare replies."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ..config import settings
from ..db import engine
from ..models.items import Association, SourceItem
from ..models.system import Setting
from ..services import shell
from ..services import slack as slack_service
from ..settings_store import get_settings

router = APIRouter(prefix="/api/on-call", tags=["on-call"])


def _load_resolved(session: Session) -> dict[str, str]:
    row = session.get(Setting, "on_call_resolved")
    if row is None or not row.value:
        return {}
    try:
        data = json.loads(row.value)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _save_resolved(session: Session, data: dict[str, str]) -> None:
    row = session.get(Setting, "on_call_resolved")
    value = json.dumps(data)
    if row is None:
        row = Setting(key="on_call_resolved", value=value)
    else:
        row.value = value
        row.updated_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    session.add(row)
    session.commit()


class OnCallScanRequest(BaseModel):
    channel: str
    frequency_minutes: int | None = None
    rotation_starts_at: str | None = None
    rotation_ends_at: str | None = None


def _parse_when(value: str | None) -> datetime | None:
    """Parse a browser datetime-local value or an ISO 8601 timestamp."""
    text = (value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        # datetime-local has no zone; the browser means local time.
        parsed = parsed.astimezone()
    return parsed


def _scan_lookback(rotation_starts_at: str | None) -> tuple[str, bool]:
    """The slackx --last value for the rotation window, and whether it has started.

    The window kept fresh is rotation start to now. Without a configured start,
    fall back to the previous one-day lookback.
    """
    start = _parse_when(rotation_starts_at)
    if start is None:
        return "1d", True
    now = datetime.now(UTC)
    if start > now:
        return "1m", False
    total_minutes = max(int((now - start).total_seconds() // 60), 1)
    days, rest = divmod(total_minutes, 24 * 60)
    hours, minutes = divmod(rest, 60)
    return "".join(
        part
        for part in (f"{days}d" if days else "", f"{hours}h" if hours else "", f"{minutes}m" if minutes else "")
        if part
    ), True


class OnCallReplyRequest(BaseModel):
    channel: str
    text: str
    thread_ts: str | None = None


class OnCallResolveRequest(BaseModel):
    channel: str
    thread_ts: str
    resolved: bool = True
    resolved_through_ts: str | None = None


@router.post("/scan")
def scan_channel(payload: OnCallScanRequest) -> dict[str, Any]:
    channel = (payload.channel or "").strip()
    if not channel:
        raise HTTPException(status_code=400, detail="channel is required")

    lookback, started = _scan_lookback(payload.rotation_starts_at)
    if not started:
        # The rotation has not started: there is no fresh window yet.
        return {"threads": [], "channel": channel, "channel_name": None, "message_count": 0, "inactive": True}

    cmd = [
        "slackx",
        "conversations",
        "get",
        channel,
        "--json",
        "--last",
        lookback,
        "--with-thread-message",
        "--fetch",
    ]
    outcome = shell._cli_run(cmd, timeout=60)
    if outcome is None:
        raise HTTPException(status_code=502, detail="slackx is not available")
    code, stdout, stderr = outcome
    if code != 0:
        raise HTTPException(status_code=502, detail=stderr or "slackx failed")
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail=f"invalid slackx output: {exc}") from exc

    messages = data.get("messages") or []
    try:
        with Session(engine) as session:
            effective = get_settings(session)
            slackx_base = (effective.get("slackx_url") or "").strip()
    except Exception:  # noqa: BLE001
        slackx_base = ""
    workspace_url = slack_service.slack_workspace_url() or "https://slack.com/"

    def _slack_url(ts: str) -> str:
        return f"https://slack.com/archives/{data.get('channel') or channel}/p{ts.replace('.', '')}"

    def _slackx_url(ts: str) -> str | None:
        if not slackx_base:
            return None
        return f"{slackx_base.rstrip('/')}/archives/{data.get('channel') or channel}/p{ts.replace('.', '')}"

    # Group replies under their thread root.
    roots: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for message in messages:
        ts = str(message.get("ts") or "")
        thread_ts = str(message.get("thread_ts") or ts)
        if message.get("is_thread_reply"):
            root = roots.get(thread_ts)
            if root is None:
                # A reply without its root in this window; treat it as a root.
                root = {
                    "id": thread_ts,
                    "ts": thread_ts,
                    "title": message.get("text", "")[:80],
                    "text": message.get("text", ""),
                    "user": message.get("user_name") or message.get("user"),
                    "replies": [],
                }
                roots[thread_ts] = root
                order.append(thread_ts)
            root.setdefault("replies", []).append(message)
        else:
            if thread_ts not in roots:
                roots[thread_ts] = {
                    "id": thread_ts,
                    "ts": thread_ts,
                    "title": message.get("text", "")[:80],
                    "text": message.get("text", ""),
                    "user": message.get("user_name") or message.get("user"),
                    "replies": [],
                }
                order.append(thread_ts)
            else:
                roots[thread_ts]["text"] = message.get("text", roots[thread_ts]["text"])
                roots[thread_ts]["title"] = (message.get("text", "") or roots[thread_ts]["title"])[:80]
                roots[thread_ts]["user"] = message.get("user_name") or message.get("user") or roots[thread_ts]["user"]

    threads = []
    for thread_ts in order:
        root = roots[thread_ts]
        replies = root.get("replies", [])
        context_lines = [f"{root['user']}: {root['text']}"]
        reply_items = []
        for reply in replies:
            reply_items.append(
                {
                    "ts": reply.get("ts"),
                    "user": reply.get("user_name") or reply.get("user"),
                    "text": reply.get("text", ""),
                }
            )
            context_lines.append(f"{reply.get('user_name') or reply.get('user')}: {reply.get('text', '')}")
        root["replies"] = reply_items
        root["context"] = "\n".join(context_lines)
        root["reply_count"] = len(reply_items)
        threads.append(root)

    for thread in threads:
        ts = str(thread.get("ts") or "")
        slack_url = f"{workspace_url.rstrip('/')}/archives/{data.get('channel') or channel}/p{ts.replace('.', '')}"
        thread["slack_url"] = slack_url
        if slackx_base:
            thread["slackx_url"] = (
                f"{slackx_base.rstrip('/')}/archives/{data.get('channel') or channel}/p{ts.replace('.', '')}"
            )
        reply_ts_list = [str(r.get("ts") or "") for r in (thread.get("replies") or [])]
        latest_ts = max([ts] + reply_ts_list)
        # Look up an existing item/task for this thread and its resolved state.
        task_id = None
        resolved = False
        resolved_through = None
        try:
            with Session(engine) as session:
                item = session.exec(select(SourceItem).where(SourceItem.url == slack_url)).first()
                if item is None:
                    item = session.exec(
                        select(SourceItem).where(SourceItem.external_id == ts, SourceItem.source == "slack")
                    ).first()
                if item is not None:
                    resolved = item.done_at is not None
                    resolved_through = item.done_message_ts
                    assoc = session.exec(select(Association).where(Association.item_id == item.id)).first()
                    if assoc is not None:
                        task_id = assoc.task_id
                    # Refresh the stored thread transcript from the freshly fetched data.
                    item.content = thread.get("context") or item.content
                    if not item.title_custom:
                        item.title = thread.get("title") or item.title
                    item.fetched_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
                    item.updated_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
                    session.add(item)
                    session.commit()
        except Exception:  # noqa: BLE001
            pass
        thread["task_id"] = task_id
        thread["resolved"] = resolved
        thread["resolved_through_ts"] = resolved_through
        thread["has_new_activity"] = bool(resolved and resolved_through and latest_ts and resolved_through < latest_ts)

    return {
        "threads": threads,
        "channel": data.get("channel"),
        "channel_name": data.get("channel_name"),
        "message_count": data.get("message_count"),
        "lookback": lookback,
    }


@router.post("/reply")
def reply_to_thread(payload: OnCallReplyRequest) -> dict[str, Any]:
    channel = (payload.channel or "").strip()
    text = (payload.text or "").strip()
    if not channel or not text:
        raise HTTPException(status_code=400, detail="channel and text are required")

    token = (settings.slack_token or "").strip()
    cookie = (settings.slack_cookie or "").strip()
    try:
        with Session(engine) as session:
            effective = get_settings(session)
            bot_token = (effective.get("slack_bot_token") or "").strip()
            if bot_token:
                token = bot_token
    except Exception:  # noqa: BLE001
        pass

    if not token:
        raise HTTPException(status_code=400, detail="SLACK_TOKEN is not configured")

    base_url = (settings.slack_api_base_url or "https://slack.com/api").rstrip("/")
    url = f"{base_url}/chat.postMessage"
    data: dict[str, Any] = {"channel": channel, "text": text}
    if payload.thread_ts:
        data["thread_ts"] = payload.thread_ts

    headers = {"Authorization": f"Bearer {token}"}
    if cookie:
        headers["Cookie"] = f"d={cookie}"

    try:
        response = httpx.post(url, data=data, headers=headers, timeout=30)
        result = response.json()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Slack request failed: {exc}") from exc

    if not isinstance(result, dict) or not result.get("ok"):
        error = result.get("error", "unknown") if isinstance(result, dict) else "unknown"
        raise HTTPException(status_code=502, detail=f"Slack refused the message: {error}")
    return {"ok": True, "ts": result.get("ts"), "channel": result.get("channel")}


@router.post("/resolve")
def resolve_thread(payload: OnCallResolveRequest) -> dict[str, Any]:
    channel = (payload.channel or "").strip()
    thread_ts = (payload.thread_ts or "").strip()
    if not channel or not thread_ts:
        raise HTTPException(status_code=400, detail="channel and thread_ts are required")
    workspace_url = slack_service.slack_workspace_url() or "https://slack.com/"
    slack_url = f"{workspace_url.rstrip('/')}/archives/{channel}/p{thread_ts.replace('.', '')}"
    with Session(engine) as session:
        item = session.exec(select(SourceItem).where(SourceItem.url == slack_url)).first()
        if item is None:
            item = session.exec(
                select(SourceItem).where(SourceItem.external_id == thread_ts, SourceItem.source == "slack")
            ).first()
        if item is None:
            item = SourceItem(source="slack", kind="thread", url=slack_url, external_id=thread_ts, title="Slack thread")
            session.add(item)
            session.commit()
            session.refresh(item)
        else:
            if item.url != slack_url:
                item.url = slack_url
        if payload.resolved:
            through = payload.resolved_through_ts or item.done_message_ts or thread_ts
            item.done_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
            item.done_message_ts = through
        else:
            item.done_at = None
            item.done_message_ts = None
        item.updated_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        session.add(item)
        session.commit()
    return {"ok": True, "resolved": payload.resolved}


@router.get("")
def read_on_call() -> dict[str, Any]:
    return {"threads": []}
