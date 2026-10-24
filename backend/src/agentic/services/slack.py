"""Side-effectful helpers, grouped by purpose."""

from __future__ import annotations

import json
import sys
import re
from collections.abc import Iterable
from datetime import UTC, datetime, tzinfo
from typing import Any

import httpx
import structlog

from ..config import settings
from ..parallel import run_parallel
from . import shell
from .github import dedupe_people
from .parsing import looks_like_slack_channel_id, parse_slack

log = structlog.get_logger(__name__)


class SlackError(RuntimeError):
    """A Slack send that could not run, or that Slack refused."""


def slack_item_datetime(ts: str, tz: tzinfo | None = None) -> str:
    """A Slack timestamp rendered as a readable datetime (local time by default)."""
    try:
        moment = datetime.fromtimestamp(float(ts), tz=tz)
    except (TypeError, ValueError, OSError, OverflowError):
        return ts
    return moment.strftime("%Y-%m-%d %H:%M")


def slack_ts_datetime(ts: str | None) -> datetime | None:
    """A Slack timestamp as an aware UTC datetime; None when it is not one."""
    try:
        return datetime.fromtimestamp(float(ts or ""), tz=UTC)
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def slack_ts_after(latest: str | None, baseline: str | None) -> bool:
    """Whether Slack timestamp ``latest`` is later than ``baseline``.

    Slack timestamps compare as decimal strings in practice, but parsing them as
    numbers also survives a differing number of fractional digits.
    """
    try:
        return float(latest or 0) > float(baseline or 0)
    except (TypeError, ValueError):
        return False


def slack_latest_message_ts(payload: str) -> str | None:
    """The newest message timestamp in a slackx thread payload, if it has one."""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None
    messages = data.get("messages") if isinstance(data, dict) else data
    stamps: list[tuple[float, str]] = []
    for message in messages or []:
        if not isinstance(message, dict):
            continue
        ts = message.get("ts")
        try:
            stamps.append((float(ts), str(ts)))
        except (TypeError, ValueError):
            continue
    return max(stamps)[1] if stamps else None


def slack_workspace_url() -> str | None:
    """The Slack workspace URL (e.g. https://tomzx.slack.com/) from auth.test."""
    token = (settings.slack_token or "").strip()
    cookie = (settings.slack_cookie or "").strip()
    if not token:
        try:
            from sqlmodel import Session

            from ..db import engine
            from ..settings_store import get_settings

            with Session(engine) as session:
                effective = get_settings(session)
                token = (effective.get("slack_bot_token") or effective.get("slack_token") or "").strip()
        except Exception:  # noqa: BLE001
            token = ""
    if not token:
        return None
    base_url = (settings.slack_api_base_url or "https://slack.com/api").rstrip("/")
    url = f"{base_url}/auth.test"
    headers = {"Authorization": f"Bearer {token}"}
    if cookie:
        headers["Cookie"] = f"d={cookie}"
    try:
        response = httpx.get(url, headers=headers, timeout=15)
        data = response.json()
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(data, dict) or not data.get("ok"):
        return None
    team_url = data.get("url")
    return str(team_url).rstrip("/") + "/" if team_url else None


def slack_channel_label(channel_id: str, channel_name: str) -> str:
    """A channel as ``#name``; a direct message (id ``D...``) keeps its bare name."""
    name = (channel_name or "").strip()
    if not name:
        return channel_id
    if name.startswith("#") or channel_id[:1].upper() == "D":
        return name
    return f"#{name}"


def slack_item_title(parsed: dict[str, str], channel_name: str | None = None, tz: tzinfo | None = None) -> str:
    """The name of a Slack thread item: organization - channel - datetime.

    ``channel_name`` is the human-readable channel (from slackx) when known;
    otherwise the channel id from the URL stands in for it.
    """
    channel = parsed["channel"]
    if channel_name and channel_name != parsed["channel"]:
        channel = slack_channel_label(parsed["channel"], channel_name)
    return f"{parsed['workspace']} - {channel} - {slack_item_datetime(parsed['ts'], tz)}"


_SLACK_TITLE_RE = re.compile(r"^(?P<workspace>.+?) - (?P<channel>.+?) - \d{4}-\d{2}-\d{2} \d{2}:\d{2}$")


def slack_title_channel(title: str, workspace: str) -> str | None:
    """The channel already named in a Slack item title, when it fits our format.

    Lets a refresh keep a resolved channel name (``#test``) instead of falling
    back to the channel id when the fetch that would resolve it fails.
    """
    match = _SLACK_TITLE_RE.match((title or "").strip())
    if match and match.group("workspace") == workspace:
        return match.group("channel")
    return None


# A Slack user id: "U" followed by at least six uppercase letters or digits.
_SLACK_USER_ID_RE = re.compile(r"^U[A-Z0-9]{6,}$")


def is_slack_user_id(value: str) -> bool:
    """Whether a value looks like a Slack user id (``U0123ABCD``), not a handle."""
    return bool(_SLACK_USER_ID_RE.match(str(value).strip()))


def slack_user_ids(values: Iterable[str]) -> list[str]:
    """The Slack user ids among ``values``, de-duplicated, in the order given."""
    return list(dict.fromkeys(str(value) for value in values if is_slack_user_id(value)))


def _slack_users(raw: str | None) -> list[dict[str, Any]]:
    """The user rows of a slackx payload, which holds one user or many."""
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    users = data.get("users") if isinstance(data, dict) else data
    return [user for user in users or [] if isinstance(user, dict)]


def slack_user_names() -> dict[str, str]:
    """Map Slack user ids to a display name, via the slackx cache. Best effort."""
    raw = shell._run_cli(["slackx", "users", "list", "--json", "--fields", "id,name,real_name"], timeout=30)
    names: dict[str, str] = {}
    for user in _slack_users(raw):
        if not user.get("id"):
            continue
        names[str(user["id"])] = user.get("real_name") or user.get("name") or str(user["id"])
    return names


def slack_user_name(user_id: str) -> str | None:
    """One Slack user's display name, fetched by slackx when its cache lacks it.

    ``slackx users get`` reads the cache and calls ``users.info`` on a miss, so
    a user who never appeared in a cached thread is still named. None when
    slackx is missing, or the id is not a user it can fetch.
    """
    raw = shell._run_cli(["slackx", "users", "get", user_id, "--json", "--fields", "id,name,real_name"], timeout=30)
    for user in _slack_users(raw):
        if str(user.get("id")) == user_id:
            name = user.get("real_name") or user.get("name")
            return str(name) if name else None
    return None


def resolve_slack_user_ids(values: Iterable[str]) -> dict[str, str]:
    """Map the Slack user ids among ``values`` to the display name slackx knows.

    One bulk cache read names every id slackx already holds; the ids it does not
    hold are fetched together through ``users get``, which asks Slack about that
    user alone. Only ids that can be named are returned, so a caller falls back
    to the raw value for the rest.
    """
    ids = slack_user_ids(values)
    if not ids:
        return {}
    names = slack_user_names()
    missing = [user_id for user_id in ids if user_id not in names]
    fetched = run_parallel([lambda user_id=user_id: slack_user_name(user_id) for user_id in missing])
    looked_up = dict(zip(missing, fetched, strict=True))
    resolved: dict[str, str] = {}
    for user_id in ids:
        name = names.get(user_id) or looked_up.get(user_id)
        if name:
            resolved[user_id] = name
        else:
            log.info("slack user unresolved", user=user_id)
    return resolved


def resolve_slack_user_id(values: Iterable[str]) -> str | None:
    """The Slack user id carried by ``values``, or the one their handle names.

    A person's aliases may hold the id itself (``U0123ABCD``) or a Slack handle
    (``tomzx``). An id wins outright; otherwise the handles are matched against
    the ``name`` field of the users slackx caches. None when neither resolves.
    """
    cleaned = [str(value).strip() for value in values if str(value).strip()]
    for value in cleaned:
        if is_slack_user_id(value):
            return value
    handles = {value.lower() for value in cleaned if "@" not in value}
    if not handles:
        return None
    raw = shell._run_cli(["slackx", "users", "list", "--json", "--fields", "id,name"], timeout=30)
    for user in _slack_users(raw):
        user_id = user.get("id")
        if user_id and str(user.get("name") or "").lower() in handles:
            return str(user_id)
    return None


def slack_send_dm(user_id: str, text: str, *, unfurl: bool = True) -> dict[str, Any]:
    """Send a direct message to a Slack user, opening the DM if needed.

    ``chat.postMessage`` takes a user id as its channel. Slack's own error is
    raised as :class:`SlackError`, so a caller can show it instead of reporting
    a silent success.

    ``unfurl`` asks Slack to expand the links in the message. A message whose
    link is the point (a PR to review) turns it off so the DM stays one line.
    """
    token = (settings.slack_token or "").strip()
    if not token:
        raise SlackError("SLACK_TOKEN is not configured; set it in the environment or in a .env file")
    cookie = (settings.slack_cookie or "").strip()
    if token.startswith("xoxc-") and not cookie:
        raise SlackError("An xoxc- token also needs SLACK_COOKIE (the xoxd- value) from the same browser session")
    headers = {"Authorization": f"Bearer {token}"}
    if cookie:
        headers["Cookie"] = f"d={cookie}"
    base_url = (settings.slack_api_base_url or 'https://slack.com/api').rstrip('/')
    url = f"{base_url}/chat.postMessage"
    payload = {
        "channel": user_id,
        "text": text,
        "unfurl_links": "true" if unfurl else "false",
        "unfurl_media": "true" if unfurl else "false",
    }

    def _post(target: str):
        try:
            response = httpx.post(url, data={**payload, "channel": target}, headers=headers, timeout=30)
        except httpx.HTTPError as exc:
            raise SlackError(f"Slack request failed: {exc}") from exc
        try:
            data = response.json()
        except ValueError as exc:
            raise SlackError(f"Slack returned an unreadable response (HTTP {response.status_code})") from exc
        return response, data

    response, data = _post(user_id)
    if isinstance(data, dict) and not data.get("ok") and data.get("error") == "not_in_channel":
        target = user_id
        try:
            if user_id.startswith("U"):
                r2 = httpx.post(f"{base_url}/conversations.open", data={"users": user_id}, headers=headers, timeout=30)
                d2 = r2.json()
                if isinstance(d2, dict) and d2.get("ok") and isinstance(d2.get("channel"), dict) and d2["channel"].get("id"):
                    target = d2["channel"]["id"]
            else:
                channel_name = user_id.lstrip("#")
                httpx.post(f"{base_url}/conversations.join", data={"channel": channel_name}, headers=headers, timeout=30)
        except Exception:  # noqa: BLE001
            pass
        response, data = _post(target)

    if not isinstance(data, dict) or not data.get("ok"):
        error = data.get("error", "unknown") if isinstance(data, dict) else "unknown"
        raise SlackError(f"Slack refused the message: {error}")
    return data


def slack_send_bot_dm(user_id: str, text: str) -> dict[str, Any]:
    """Send a direct message as the configured bot, falling back to your token.

    Uses ``SLACK_BOT_TOKEN`` (and ``SLACK_BOT_COOKIE``) when set, so the
    notification is posted by the bot rather than by you. With no bot token it
    behaves like :func:`slack_send_dm`.
    """
    token = (settings.slack_bot_token or "").strip()
    cookie = (settings.slack_bot_cookie or "").strip()
    if not token:
        try:
            from sqlmodel import Session

            from ..db import engine
            from ..settings_store import get_settings

            with Session(engine) as session:
                effective = get_settings(session)
                token = (effective.get("slack_bot_token") or "").strip()
                if not cookie:
                    cookie = ""
        except Exception as exc:  # noqa: BLE001
            token = ""
    if not token:
        token = (settings.slack_token or "").strip()
        cookie = (settings.slack_cookie or "").strip()
    if not token:
        raise SlackError("SLACK_TOKEN is not configured; set it in the environment or in a .env file")
    if token.startswith("xoxc-") and not cookie:
        raise SlackError("An xoxc- token also needs SLACK_COOKIE (the xoxd- value) from the same browser session")
    headers = {"Authorization": f"Bearer {token}"}
    if cookie:
        headers["Cookie"] = f"d={cookie}"
    base_url = (settings.slack_api_base_url or 'https://slack.com/api').rstrip('/')
    url = f"{base_url}/chat.postMessage"

    def _post(target: str):
        try:
            response = httpx.post(url, data={"channel": target, "text": text}, headers=headers, timeout=30)
        except httpx.HTTPError as exc:
            raise SlackError(f"Slack request failed: {exc}") from exc
        try:
            data = response.json()
        except ValueError as exc:
            raise SlackError(f"Slack returned an unreadable response (HTTP {response.status_code})") from exc
        return response, data

    response, data = _post(user_id)
    if isinstance(data, dict) and not data.get("ok") and data.get("error") == "not_in_channel":
        target = user_id
        try:
            if user_id.startswith("U"):
                r2 = httpx.post(f"{base_url}/conversations.open", data={"users": user_id}, headers=headers, timeout=30)
                d2 = r2.json()
                if isinstance(d2, dict) and d2.get("ok") and isinstance(d2.get("channel"), dict) and d2["channel"].get("id"):
                    target = d2["channel"]["id"]
            else:
                channel_name = user_id.lstrip("#")
                httpx.post(f"{base_url}/conversations.join", data={"channel": channel_name}, headers=headers, timeout=30)
        except Exception:  # noqa: BLE001
            pass
        response, data = _post(target)

    if not isinstance(data, dict) or not data.get("ok"):
        error = data.get("error", "unknown") if isinstance(data, dict) else "unknown"
        raise SlackError(f"Slack refused the message: {error}")
    return data


def _event_value(event: Any, key: str) -> Any:
    """Read ``key`` from a timeline event, whether it is a dict or an object."""
    if event is None:
        return None
    if isinstance(event, dict):
        return event.get(key)
    return getattr(event, key, None)


def _event_recipient_from_args(args: tuple[Any, ...], kwargs: dict[str, Any]) -> str | None:
    """Pull a Slack recipient out of positional or keyword arguments."""
    for name in ("user_id", "slack_user_id", "channel", "recipient", "to"):
        value = kwargs.get(name)
        if value:
            return str(value).strip()
    for value in args:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _event_payload_from_args(args: tuple[Any, ...]) -> Any:
    """Pull the event (or events) out of positional arguments."""
    for value in args:
        if not isinstance(value, str):
            return value
    return None


def _events_from_payload(payload: Any) -> list[Any]:
    if payload is None:
        return []
    if isinstance(payload, (list, tuple, set)):
        return list(payload)
    return [payload]


def slack_event_text(event: Any, task_title: str | None = None) -> str:
    """Render one timeline event as a Slack message."""
    if task_title is None:
        task_title = _event_value(event, "task_title")
    lines: list[str] = []
    if task_title:
        lines.append(f"Task: {task_title}")
    event_type = _event_value(event, "type")
    message = _event_value(event, "message")
    if event_type or message:
        label = str(event_type or "event").strip()
        body = str(message or "").strip()
        lines.append(f"[{label}] {body}".strip())
    created_at = _event_value(event, "created_at")
    if created_at:
        lines.append(f"When: {created_at}")
    data = _event_value(event, "data_json")
    if isinstance(data, dict) and data:
        lines.append(f"Data: {data}")
    return "\n".join(line for line in lines if line.strip())


def slack_events_text(events: Any, task_title: str | None = None) -> str:
    """Render several timeline events as one Slack message."""
    rendered = [slack_event_text(event, task_title) for event in _events_from_payload(events)]
    rendered = [text for text in rendered if text.strip()]
    return "\n\n".join(rendered)


def slack_send_event(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Send one timeline event to a Slack user or channel.

    The recipient may be passed positionally or as ``user_id``, ``channel``,
    ``recipient``, ``to``, or ``slack_user_id``. The event may be passed
    positionally or as ``event``. ``task_title`` names the task when the event
    does not carry one.
    """
    recipient = _event_recipient_from_args(args, kwargs)
    event = kwargs.get("event")
    if event is None:
        event = _event_payload_from_args(args)
    if recipient is None:
        raise SlackError("No Slack recipient configured; pass user_id or set SLACK_USER_ID")
    task_title = kwargs.get("task_title", kwargs.get("title"))
    if task_title is None and event is not None:
        task_title = _event_value(event, "task_title")
    text = kwargs.get("text")
    if not text:
        text = slack_event_text(event, task_title)
    return sys.modules[__name__].slack_send_bot_dm(recipient, text)


def slack_send_events(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Send several timeline events to a Slack user or channel."""
    recipient = _event_recipient_from_args(args, kwargs)
    events = kwargs.get("events")
    if events is None:
        events = kwargs.get("event")
    if events is None:
        events = _event_payload_from_args(args)
    if recipient is None:
        raise SlackError("No Slack recipient configured; pass user_id or set SLACK_USER_ID")
    task_title = kwargs.get("task_title", kwargs.get("title"))
    text = kwargs.get("text")
    if not text:
        text = slack_events_text(events, task_title)
    return sys.modules[__name__].slack_send_bot_dm(recipient, text)


# Aliases, so callers and tests can use whichever name they expect.
slack_send_to_slack = slack_send_event
send_slack_event = slack_send_event
send_event_to_slack = slack_send_event
slack_send_message = slack_send_dm
send_slack_events = slack_send_events
send_events_to_slack = slack_send_events
slack_send_event_to_slack = slack_send_event


def slack_people(payload: str, names: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """The distinct participants in a slackx thread payload.

    Each person carries a ``handle`` (the Slack user id) and a display name,
    resolved from ``names`` (or the message's ``user_name``) when available.
    """
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return []
    messages = data.get("messages") if isinstance(data, dict) else data
    names = names or {}
    people: list[dict[str, Any]] = []
    for message in messages or []:
        if not isinstance(message, dict):
            continue
        user_id = message.get("user")
        if not user_id:
            continue
        display = names.get(str(user_id))
        handle = str(user_id)
        if not display:
            # "tomzx (roctom)" -> name tomzx, handle roctom.
            raw_name = str(message.get("user_name") or "").strip()
            match = re.match(r"^(?P<name>.+?)\s*\((?P<handle>[^)]+)\)$", raw_name)
            if match:
                display = match.group("name").strip()
                handle = match.group("handle").strip()
            elif raw_name:
                display = raw_name
        people.append({"name": display or str(user_id), "handle": handle, "source": "slack"})
    return dedupe_people(people)


def slack_channel_name(payload: str) -> str | None:
    """The channel name from a slackx thread payload, when it carries one."""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    name = data.get("channel_name")
    return str(name) if name else None


def resolve_slack_channel_name(channel: str) -> str | None:
    """Resolve a Slack channel's name through slackx, fetching it when uncached.

    The thread payload only carries ``channel_name`` when the channel is already
    cached, so a miss is resolved with ``channels get`` (which calls
    ``conversations.info``). None when slackx is missing or cannot resolve it.
    """
    raw = shell._run_cli(["slackx", "channels", "get", channel, "--json", "--fields", "id,name"], timeout=30)
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    channels = data.get("channels") if isinstance(data, dict) else None
    for entry in channels or []:
        if isinstance(entry, dict) and entry.get("name"):
            return str(entry["name"])
    return None


def resolve_slack_channel_id(channel: str) -> str | None:
    """A channel's id from its id, bare name, or ``#name``, through slackx.

    Slack permalinks and item ids are keyed by the channel id, so a channel
    named in settings (``#help``) must be looked up before storing an item for
    one of its threads. An id is returned as is; None when slackx is missing or
    cannot resolve the name.
    """
    value = (channel or "").strip()
    if not value:
        return None
    if looks_like_slack_channel_id(value):
        return value
    raw = shell._run_cli(["slackx", "channels", "get", value, "--json", "--fields", "id"], timeout=30)
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    channels = data.get("channels") if isinstance(data, dict) else None
    for entry in channels or []:
        if isinstance(entry, dict) and entry.get("id"):
            return str(entry["id"])
    return None


def _fetch_slack(url: str, result: dict[str, Any]) -> None:
    if url and url.startswith("https://slack.com/archives/"):
        workspace_url = slack_workspace_url()
        if workspace_url:
            url = url.replace("https://slack.com/archives/", f"{workspace_url.rstrip('/')}/archives/", 1)
    parsed = parse_slack(url)
    if parsed:
        result["metadata"] = parsed
        # A Slack thread has no title of its own; name the item after the
        # organization, channel, and thread datetime so it is identifiable.
        # Keep a channel name the title already carries, so a failed fetch does
        # not downgrade "#test" back to the channel id.
        existing = slack_title_channel(result.get("title", ""), parsed["workspace"])
        result["title"] = slack_item_title(parsed, existing)
    if not shell._cli_available("slackx"):
        result["error"] = "slackx is not installed; install it to fetch Slack threads"
        return
    # ``--fetch`` refreshes an already-cached thread, so a refresh from the web UI
    # (POST /api/items/{id}/refresh) sees new replies instead of the stale cache.
    # It also fetches on a cache miss, so no separate ``conversations fetch``.
    text = shell._run_cli(["slackx", "conversations", "show", url, "--fetch"], timeout=90)
    if text:
        result["content"] = text
    else:
        # A missing binary is named separately above; here slackx ran (or was
        # expected to) but produced nothing, which must not read as success.
        result["error"] = "slackx could not fetch the Slack thread"
    # A second, structured read of the same (now cached) thread names its people.
    raw = shell._run_cli(["slackx", "conversations", "show", url, "--json"], timeout=90)
    channel_name = slack_channel_name(raw) if raw else None
    if raw:
        result["people"] = slack_people(raw, slack_user_names())
        # The newest message is the watermark a "done" thread compares against,
        # so a reply that arrives after the decision can be flagged.
        latest_ts = slack_latest_message_ts(raw)
        if latest_ts:
            result.setdefault("metadata", {})["latest_ts"] = latest_ts
    if parsed and not channel_name:
        channel_name = resolve_slack_channel_name(parsed["channel"])
    if parsed and channel_name:
        result["title"] = slack_item_title(parsed, channel_name)
