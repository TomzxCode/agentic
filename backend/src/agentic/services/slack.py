"""Side-effectful helpers, grouped by purpose."""

from __future__ import annotations

import json
import re
from datetime import datetime, tzinfo
from typing import Any

from . import shell
from .github import dedupe_people
from .parsing import parse_slack


def slack_item_datetime(ts: str, tz: tzinfo | None = None) -> str:
    """A Slack timestamp rendered as a readable datetime (local time by default)."""
    try:
        moment = datetime.fromtimestamp(float(ts), tz=tz)
    except (TypeError, ValueError, OSError, OverflowError):
        return ts
    return moment.strftime("%Y-%m-%d %H:%M")


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


def slack_user_names() -> dict[str, str]:
    """Map Slack user ids to a display name, via the slackx cache. Best effort."""
    raw = shell._run_cli(["slackx", "users", "list", "--json", "--fields", "id,name,real_name"], timeout=30)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    users = data.get("users") if isinstance(data, dict) else data
    names: dict[str, str] = {}
    for user in users or []:
        if not isinstance(user, dict) or not user.get("id"):
            continue
        names[str(user["id"])] = user.get("real_name") or user.get("name") or str(user["id"])
    return names


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
    if parsed and not channel_name:
        channel_name = resolve_slack_channel_name(parsed["channel"])
    if parsed and channel_name:
        result["title"] = slack_item_title(parsed, channel_name)
