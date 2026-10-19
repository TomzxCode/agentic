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
    title: str = ""
    url: str = ""
    author: str = ""
    # GitHub's own state and creation time, carried so the queue can show them.
    state: str = ""
    draft: bool = False
    created_at: str | None = None
    first_seen_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
