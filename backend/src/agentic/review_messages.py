"""Render the Slack DM a review poke sends.

Both the manual poke and the review auto-poke share the same variables and
formatting; they only differ in which template setting supplies the text.
"""

from __future__ import annotations

from datetime import timedelta
from string import Formatter

import structlog

from .services.github import pr_slack_link

log = structlog.get_logger(__name__)

#: The default DM. ``link`` is the pull request as a Slack link.
DEFAULT_MESSAGE = ":wave::robot_face: I would love your review on this PR: {link}"
#: The placeholders a custom poke message may use.
MESSAGE_VARIABLES = frozenset({"link", "url", "title", "slo", "elapsed"})


def format_duration(value: timedelta) -> str:
    """A duration as the compact text a message reads, e.g. ``1d 6h``."""
    seconds = max(int(value.total_seconds()), 0)
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes = seconds // 60
    if days:
        return f"{days}d {hours}h" if hours else f"{days}d"
    if hours:
        return f"{hours}h {minutes}m" if minutes else f"{hours}h"
    return f"{minutes}m" if minutes else "less than a minute"


def validate_message_template(value: str | None) -> None:
    """Reject a message template that uses a variable the app does not provide."""
    text = (value or "").strip()
    if not text:
        return
    try:
        fields = [field for _, field, _, _ in Formatter().parse(text) if field is not None]
    except ValueError as exc:
        raise ValueError(f"malformed template: {exc}") from exc
    unknown = sorted({field for field in fields if field not in MESSAGE_VARIABLES})
    if unknown:
        allowed = ", ".join(f"{{{name}}}" for name in sorted(MESSAGE_VARIABLES))
        raise ValueError(f"unknown variable {unknown[0]}; use one of {allowed}")


def render_message(
    template: str | None,
    *,
    url: str,
    title: str,
    slo: timedelta | None,
    elapsed: timedelta | None,
) -> str:
    """Render a poke message, falling back to the default on a bad template.

    ``slo`` and ``elapsed`` are optional for a manual poke that cannot work out
    the pull request's age; their placeholders then render empty.
    """
    text = (template or "").strip() or DEFAULT_MESSAGE
    values = {
        "link": pr_slack_link(url, title),
        "url": url,
        "title": title,
        "slo": format_duration(slo) if slo is not None else "",
        "elapsed": format_duration(elapsed) if elapsed is not None else "",
    }
    try:
        return text.format_map(values)
    except (KeyError, ValueError):
        log.warning("poke message template could not be rendered; using the default")
        return DEFAULT_MESSAGE.format_map(values)


__all__ = [
    "DEFAULT_MESSAGE",
    "MESSAGE_VARIABLES",
    "format_duration",
    "render_message",
    "validate_message_template",
]
