"""Pull requests the review scan found awaiting the user's feedback."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlmodel import Field, SQLModel, UniqueConstraint

from .base import new_id, utcnow


class ReviewScanSource(StrEnum):
    """How a pull request entered the scan.

    ``requested`` is a review GitHub asked of the user, ``reviewed`` is an open
    pull request they have already reviewed (kept visible until it closes or is
    approved), mirroring the two searches the ``review_requested_prs`` script
    runs.
    """

    requested = "requested"
    reviewed = "reviewed"


class ReviewAutoPoke(SQLModel, table=True):
    """How many scheduled auto-poke rounds a pull request has already had.

    One row per pull request the auto-poke job is poking. It is not an audit
    log: it exists so a tick or a restart does not send the same round twice.
    The row is kept when the pull request leaves the set (reviewed, closed, back
    to draft, or no requested reviewer), so a read that omits it for a tick does
    not make it look unpoked when it returns; a new ready-for-review round
    resets its rounds.
    """

    __table_args__ = (UniqueConstraint("repository", "number", name="uq_review_auto_poke"),)

    id: str = Field(default_factory=new_id, primary_key=True)
    # "owner/name", normalized to lowercase so the key matches across sources.
    repository: str = Field(index=True)
    number: int
    # The schedule text the delivered rounds were counted against. A changed
    # schedule starts the rounds over.
    schedule: str = ""
    # How many scheduled rounds have been delivered, including a round whose
    # reviewers could not all be reached.
    poked_rounds: int = 0
    last_poked_at: datetime | None = None
    # When the current schedule started for this pull request. ``next+...``
    # uses it to find the first boundary; the other forms keep it for a stable
    # reset point and for display.
    anchor_at: datetime | None = None
    updated_at: datetime = Field(default_factory=utcnow)


class ReviewRequest(SQLModel, table=True):
    """A pull request the review scan found awaiting the user's feedback.

    GitHub is the source of truth: every scan replaces this set, so a row exists
    only while the pull request still awaits a review. ``first_seen_at`` survives
    across scans, so the queue can tell how long it has been waiting.
    """

    __table_args__ = (UniqueConstraint("repository", "number", name="uq_review_request"),)

    id: str = Field(default_factory=new_id, primary_key=True)
    # "owner/name", in GitHub's own casing.
    repository: str = Field(index=True)
    number: int
    # One of ReviewScanSource.
    source: str = ReviewScanSource.requested.value
    # Who the review is still requested from: "me", "team", or "both". The
    # search asks GitHub for ``@me``, which covers the user and the teams they
    # belong to; the row's pending requests say which of the two matched. A row
    # the scan did not find (a report-only row) is personal by default.
    review_scope: str = "me"
    title: str = ""
    url: str = ""
    author: str = ""
    # GitHub's own state and creation time, carried so the queue can show them.
    state: str = ""
    draft: bool = False
    created_at: str | None = None
    # When the pull request was last marked ready for review, from the scan's
    # timeline read. The review SLO counts from here, since that is when a
    # review could be requested; None when the timeline has no such event, and
    # the SLO falls back to first_seen_at.
    ready_for_review_at: datetime | None = None
    first_seen_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
