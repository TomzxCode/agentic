"""Tiered refresh policy for Slack and GitHub source items.

A thread, issue, or pull request changes at a different rate over its life: a
just-opened one may see replies within the hour, while one from last month is
effectively settled. Refreshing every item at one fixed interval either wastes
work on old items or misses activity on new ones.

A policy is a list of age bands, each pairing an upper age bound with a refresh
interval, plus an optional fallback interval for items older than the last band::

    1d=1h,7d=6h,30d=1d,*=7d

reads: while the item is newer than a day, refresh it at most hourly; newer
than a week, every six hours; newer than 30 days, daily; older than that,
weekly. Omit the ``*=`` term (or write ``*=never``) to stop refreshing an item
once it outgrows the last band. Empty text disables refresh entirely.

This module is pure: parsing and the due calculation take plain values, so the
rules can be tested without a database or a clock. The database-side runner
lives in ``routers/items.py``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from .services.parsing import parse_slack

_DURATION_RE = re.compile(r"^(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>[smhdw])$", re.IGNORECASE)
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}

# Sources whose content comes from slackx/ghx, so a refresh actually does work.
REFRESHABLE_SOURCES = ("slack", "github")

# The setting key that holds each source's policy, so the router, the background
# loop, and the CLI agree on where a source's schedule is configured.
POLICY_SETTING_KEYS = {
    "slack": "slack_refresh_policy",
    "github": "github_refresh_policy",
}


class PolicyError(ValueError):
    """A refresh policy string that cannot be parsed."""


@dataclass(frozen=True)
class RefreshTier:
    """Refresh at ``interval`` while the item is newer than ``max_age``."""

    max_age: timedelta
    interval: timedelta | None


@dataclass(frozen=True)
class RefreshPolicy:
    """Age bands in ascending order, plus the fallback past the last one."""

    tiers: tuple[RefreshTier, ...] = ()
    fallback: timedelta | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.tiers) or self.fallback is not None


def parse_duration(text: str) -> timedelta | None:
    """Parse ``30m``/``1h``/``6h``/``1d``/``7d``/``2w``; None when malformed."""
    match = _DURATION_RE.match((text or "").strip())
    if not match:
        return None
    return timedelta(seconds=float(match.group("value")) * _UNIT_SECONDS[match.group("unit").lower()])


def _parse_interval(text: str) -> timedelta | None:
    cleaned = (text or "").strip().lower()
    if cleaned in ("never", "none", "off", "-"):
        return None
    duration = parse_duration(cleaned)
    if duration is None:
        raise PolicyError(f"'{text}' is not a duration (use 30m, 1h, 6h, 1d, 7d, 2w, or never)")
    return duration


def parse_policy(text: str | None) -> RefreshPolicy:
    """Parse ``1d=1h,7d=6h,30d=1d,*=7d`` into a policy. Empty text disables it."""
    tokens = [token.strip() for token in (text or "").split(",") if token.strip()]
    if not tokens:
        return RefreshPolicy()
    tiers: list[RefreshTier] = []
    fallback: timedelta | None = None
    has_fallback = False
    for token in tokens:
        if "=" not in token:
            raise PolicyError(f"'{token}' is missing '=' (write it as age=interval)")
        key, value = (part.strip() for part in token.split("=", 1))
        if key == "*":
            if has_fallback:
                raise PolicyError("only one '*' fallback is allowed")
            fallback = _parse_interval(value)
            has_fallback = True
            continue
        max_age = parse_duration(key)
        if max_age is None:
            raise PolicyError(f"'{key}' is not an age (use 30m, 1d, 7d, 30d, ...)")
        tiers.append(RefreshTier(max_age=max_age, interval=_parse_interval(value)))
    for earlier, later in zip(tiers, tiers[1:], strict=False):
        if later.max_age <= earlier.max_age:
            raise PolicyError("age bands must strictly increase (e.g. 1d=1h,7d=6h,30d=1d)")
    return RefreshPolicy(tiers=tuple(tiers), fallback=fallback)


def interval_for_age(policy: RefreshPolicy, age: timedelta) -> timedelta | None:
    """The refresh interval for an item of ``age``, or None when it never refreshes."""
    for tier in policy.tiers:
        if age < tier.max_age:
            return tier.interval
    return policy.fallback


def is_due(policy: RefreshPolicy, *, age: timedelta, fetched_at: datetime | None, now: datetime) -> bool:
    """True when an item of ``age``, last fetched at ``fetched_at``, is due."""
    interval = interval_for_age(policy, age)
    if interval is None:
        return False
    if fetched_at is None:
        return True
    return now - as_utc(fetched_at) >= interval


def as_utc(value: datetime) -> datetime:
    """Treat a naive datetime read back from SQLite as UTC."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _parse_iso(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return as_utc(parsed)


def item_start(item: Any) -> datetime:
    """When the item's upstream object began, falling back to when it was recorded.

    GitHub stores the issue/PR ``created_at`` in its metadata; a Slack URL
    carries the thread timestamp. Both give the item's true age, so a
    just-imported old issue is not treated as brand new.
    """
    created = (item.metadata_json or {}).get("created_at")
    if isinstance(created, str) and created:
        parsed = _parse_iso(created)
        if parsed is not None:
            return parsed
    if item.source == "slack" and item.url:
        slack = parse_slack(item.url)
        if slack:
            try:
                return datetime.fromtimestamp(float(slack["ts"]), tz=UTC)
            except (TypeError, ValueError):
                pass
    return as_utc(item.created_at)


def item_age(item: Any, now: datetime) -> timedelta:
    """How long ago the item's upstream object began."""
    return now - item_start(item)


def policies_from_settings(effective: dict[str, str]) -> dict[str, str]:
    """Pull each source's policy text out of the effective settings."""
    return {source: effective.get(key, "") for source, key in POLICY_SETTING_KEYS.items()}


def describe_policy(text: str | None) -> dict[str, Any]:
    """Parse a policy and report its bands, for a UI/CLI preview.

    Raises ``PolicyError`` when the text is malformed; callers decide how to
    surface that (the preview endpoint reports it as ``valid: false``).
    """
    policy = parse_policy(text)
    return {
        "valid": True,
        "error": None,
        "enabled": policy.enabled,
        "tiers": [
            {
                "max_age_seconds": tier.max_age.total_seconds(),
                "interval_seconds": tier.interval.total_seconds() if tier.interval else None,
            }
            for tier in policy.tiers
        ],
        "fallback_seconds": policy.fallback.total_seconds() if policy.fallback else None,
    }


__all__ = [
    "POLICY_SETTING_KEYS",
    "REFRESHABLE_SOURCES",
    "PolicyError",
    "RefreshPolicy",
    "RefreshTier",
    "as_utc",
    "describe_policy",
    "interval_for_age",
    "is_due",
    "item_age",
    "item_start",
    "parse_duration",
    "parse_policy",
    "policies_from_settings",
]
