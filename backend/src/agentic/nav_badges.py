"""The counts the sidebar nav badges show.

Each badge answers one question: how much is waiting on the viewer on that page.
The counts come from the same stores the pages read, but without a page load's
live GitHub refresh: the review queue's stored scan finds, the cached My PRs
listing, and the reviewer-feedback files. A badge is therefore a nudge rather
than a substitute for the page's own header, which reads GitHub afresh.

Every count means what the page shows at rest:

- ``reviews``: open pull requests in the review queue that are not drafts and
  not already approved.
- ``my_pulls``: the authored pull requests that need the author to act (failing
  checks, requested changes, or an open review thread).
- ``feedback``: reviewer comments still awaiting a decision.
"""

from __future__ import annotations

from typing import Any

from sqlmodel import Session

from .config import settings
from .feedback_store import discover_feedback
from .my_pulls import fetch_my_pulls, known_github_repositories, pull_counts
from .review_queue import collect_review_prs, scan_row
from .review_scan import stored_review_requests
from .settings_store import resolve_github_login

#: The pull request states that no longer await a review. A row whose state was
#: never read is treated as open, matching the review queue's own fallback.
_CLOSED_STATES = frozenset({"MERGED", "CLOSED"})


def _key(repository: str, number: int) -> tuple[str, int]:
    return (str(repository).lower(), int(number))


def awaiting_review(pr: dict[str, Any]) -> bool:
    """Whether the review queue shows a pull request at rest.

    The queue hides drafts and already approved pull requests by default,
    because neither still waits for a reviewer. A merged or closed pull request
    is out too, so the badge counts only work that is still open.
    """
    if pr.get("draft"):
        return False
    if str(pr.get("state") or "").upper() in _CLOSED_STATES:
        return False
    return str(pr.get("review_decision") or "").upper() != "APPROVED"


def review_count(session: Session) -> int:
    """The pull requests awaiting a review in the queue's default view."""
    rows = collect_review_prs()
    seen = {_key(row["repository"], row["number"]) for row in rows}
    candidates = list(rows)
    for recorded in stored_review_requests(session):
        key = _key(recorded.repository, recorded.number)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(scan_row(recorded))
    return sum(1 for row in candidates if awaiting_review(row))


def my_pulls_count(session: Session) -> int:
    """The authored pull requests that need their author to act.

    This reads the same cached listing the My PRs page and the inbox nudge use
    (``fetch_my_pulls`` never forces a refresh), so opening the app does not add
    a GitHub query. With no login or repository configured, it is zero.
    """
    report = fetch_my_pulls(resolve_github_login(session), known_github_repositories(session))
    return int(pull_counts(report["pulls"])["attention"])


def feedback_count() -> int:
    """The reviewer comments still awaiting a decision."""
    return sum(1 for item in discover_feedback(settings.sdlc_dir.expanduser()) if item.decision is None)


__all__ = ["awaiting_review", "feedback_count", "my_pulls_count", "review_count"]
