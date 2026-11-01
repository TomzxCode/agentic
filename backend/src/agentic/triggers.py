"""Execution graph triggers: the ways a graph starts without a manual run.

Each trigger is its own row with a type and a type-specific config, so the cron
schedule is one kind of trigger rather than a column on the graph. A type owns
its config shape, the problems found in it, and when it fires next; the firing
itself stays with whatever knows the events (the cron scheduler for a schedule,
the webhook endpoint for a webhook).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from . import schedules

SCHEDULE = "schedule"
WEBHOOK = "webhook"
# The types the API accepts, in the order the editor offers them.
TRIGGER_TYPES = (SCHEDULE, WEBHOOK)


def normalize(raw: dict[str, Any]) -> dict[str, Any]:
    """The stored shape of one submitted trigger.

    Unknown keys are dropped and the config is reduced to the keys its type
    uses, so a saved trigger carries nothing the runner cannot understand.
    """
    ttype = str(raw.get("type") or SCHEDULE)
    raw_config = raw.get("config")
    config: dict[str, Any] = raw_config if isinstance(raw_config, dict) else {}
    clean: dict[str, Any] = {"id": str(raw.get("id") or ""), "type": ttype, "enabled": bool(raw.get("enabled", True))}
    if ttype == SCHEDULE:
        clean["config"] = {
            "cron": str(config.get("cron") or "").strip(),
            "timezone": str(config.get("timezone") or "").strip(),
        }
    elif ttype == WEBHOOK:
        clean["config"] = {"secret": str(config.get("secret") or "")}
    else:
        clean["config"] = {}
    return clean


def issues(trigger: dict[str, Any]) -> list[str]:
    """Every problem with one normalized trigger, in plain English."""
    ttype = trigger.get("type")
    if ttype not in TRIGGER_TYPES:
        return [f"Unknown trigger type '{ttype}'"]
    if ttype != SCHEDULE:
        return []
    problems: list[str] = []
    config = trigger.get("config") or {}
    cron = config.get("cron") or ""
    if not cron:
        problems.append("A schedule trigger needs a cron expression")
    else:
        try:
            schedules.validate_schedule(cron)
        except ValueError as exc:
            problems.append(str(exc))
    zone = config.get("timezone") or ""
    if zone:
        try:
            schedules.resolve_timezone(zone)
        except ValueError as exc:
            problems.append(str(exc))
    return problems


def next_run(trigger: dict[str, Any], *, base: datetime | None = None) -> datetime | None:
    """When an enabled schedule trigger fires next; None for the other types."""
    if trigger.get("type") != SCHEDULE or not trigger.get("enabled", True):
        return None
    config = trigger.get("config") or {}
    cron = config.get("cron") or ""
    if not cron:
        return None
    return schedules.compute_next_run(cron, base=base, timezone=config.get("timezone") or None)


def summary(trigger: dict[str, Any]) -> str:
    """A short label for lists: 'schedule 0 9 * * *' or 'webhook'."""
    ttype = trigger.get("type") or ""
    if ttype == SCHEDULE:
        return f"schedule {(trigger.get('config') or {}).get('cron') or '-'}"
    return ttype or "trigger"
