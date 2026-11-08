"""Send a pull request's reviewers the Slack DM a poke asks for.

The item view, the standalone pull request view, and the review auto-poke job
all ask a reviewer for a review over Slack from the same people lookup, so the
work lives here rather than in any one caller.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlmodel import Session

from .models.base import utcnow
from .review_messages import render_message
from .review_scan import slo_interval
from .routers.people_service import person_aliases, person_for_alias
from .services.github import fetch_github_pull_review_reference
from .services.parsing import parse_github
from .services.slack import SlackError, resolve_slack_user_id, slack_send_dm
from .settings_store import get_settings


@dataclass
class PokeOutcome:
    """The reviewers a poke reached and the ones it could not."""

    poked: list[dict[str, Any]] = field(default_factory=list)
    failed: list[dict[str, Any]] = field(default_factory=list)


def manual_review_message(session: Session, *, url: str, title: str) -> str:
    """Render the configured message for a manually triggered poke.

    The SLO is the review nudge SLO, and the age runs from the pull request's
    review start. Either is left blank when it is unknown, so a poke still goes
    out when ghx cannot answer.
    """
    values = get_settings(session)
    template = values.get("review_poke_message", "")
    slo = slo_interval(values.get("review_nudge_slo", ""))
    parsed = parse_github(url or "")
    reference = None
    if parsed is not None and parsed.get("kind") == "pull_request":
        reference = fetch_github_pull_review_reference(parsed["owner"], parsed["repo"], parsed["number"])
    elapsed = utcnow() - reference if reference is not None else None
    return render_message(template, url=url, title=title, slo=slo, elapsed=elapsed)


def poke_reviewers(
    session: Session,
    *,
    url: str,
    title: str,
    logins: list[str] | tuple[str, ...],
    message: str | None = None,
) -> PokeOutcome:
    """DM each named reviewer the pull request's review request.

    The GitHub logins resolve through the people directory, the way the item
    page's poke does. Each reviewer is reported on its own: one person missing
    their Slack id does not stop the others from being reached. Logins are
    deduplicated case-insensitively, so requesting the same reviewer twice sends
    one message. ``message`` overrides the default text (the auto-poke job
    renders its configurable template).
    """
    outcome = PokeOutcome()
    text = message or manual_review_message(session, url=url, title=title)
    seen: set[str] = set()
    for login in logins:
        cleaned = (login or "").strip()
        if not cleaned or cleaned.lower() in seen:
            continue
        seen.add(cleaned.lower())
        person = person_for_alias(session, cleaned)
        if person is None:
            outcome.failed.append(
                {
                    "login": cleaned,
                    "reason": (
                        f"No person carries the GitHub login @{cleaned}. Create them in People with that login, "
                        "then poke again."
                    ),
                }
            )
            continue
        slack_user_id = resolve_slack_user_id(person_aliases(session, person.id))
        if slack_user_id is None:
            outcome.failed.append(
                {
                    "login": cleaned,
                    "reason": (
                        f"{person.name} has no Slack user id or handle among their aliases. "
                        "Add one on their person page, then poke again."
                    ),
                }
            )
            continue
        try:
            # The PR link is the whole message, so no preview: the DM stays one line.
            sent = slack_send_dm(slack_user_id, text, unfurl=False)
        except SlackError as exc:
            outcome.failed.append({"login": cleaned, "reason": str(exc)})
            continue
        outcome.poked.append(
            {
                "login": cleaned,
                "name": person.name,
                "slack_user_id": slack_user_id,
                "ts": str(sent["ts"]) if sent.get("ts") else None,
            }
        )
    return outcome


__all__ = ["PokeOutcome", "poke_reviewers"]
