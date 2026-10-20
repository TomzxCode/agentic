"""Side-effectful helpers, grouped by purpose."""

from __future__ import annotations

import json
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
from .parsing import parse_slack

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


def slack_send_dm(user_id: str, text: str) -> dict[str, Any]:
    """Send a direct message to a Slack user, opening the DM if needed.

    ``chat.postMessage`` takes a user id as its channel. Slack's own error is
    raised as :class:`SlackError`, so a caller can show it instead of reporting
    a silent success.
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
    url = f"{(settings.slack_api_base_url or 'https://slack.com/api').rstrip('/')}/chat.postMessage"
    try:
        response = httpx.post(url, data={"channel": user_id, "text": text}, headers=headers, timeout=30)
    except httpx.HTTPError as exc:
        raise SlackError(f"Slack request failed: {exc}") from exc
    try:
        data = response.json()
    except ValueError as exc:
        raise SlackError(f"Slack returned an unreadable response (HTTP {response.status_code})") from exc
    if not isinstance(data, dict) or not data.get("ok"):
        error = data.get("error", "unknown") if isinstance(data, dict) else "unknown"
        raise SlackError(f"Slack refused the message: {error}")
    return data


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
    cached, so a miss is resolved with ``channels list`` (which calls
    ``conversations.info``). None when slackx is missing or cannot resolve it.
    """
    raw = shell._run_cli(["slackx", "channels", "list", channel, "--json", "--fields", "id,name"], timeout=30)
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


def _fetch_slack(url: str, result: dict[str, Any]) -> None:
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
