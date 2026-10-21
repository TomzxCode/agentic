"""My PRs response models.

The rows are read from GitHub, not stored, so these models carry the fields the
page renders: the pull request's identity, its check rollup, its review state
and approvers, and how many review threads are still open.
"""

from __future__ import annotations

from pydantic import BaseModel

from .base import UtcDateTime


class MyPullRead(BaseModel):
    repository: str
    number: int
    title: str = ""
    url: str = ""
    draft: bool = False
    created_at: str | None = None
    updated_at: str | None = None
    # GitHub's review decision (APPROVED / CHANGES_REQUESTED / REVIEW_REQUIRED),
    # or "" when no review has decided it.
    review_decision: str = ""
    # Whether the review decision is APPROVED, which means the reviews the branch
    # requires are in, not merely that someone approved.
    approved: bool = False
    # The logins whose latest opinionated review approves the pull request.
    approvers: list[str] = []
    # success / pending / failure / none, from the head commit's check rollup.
    ci: str = "none"
    # Unresolved review threads, and every thread the read carried.
    open_threads: int = 0
    threads_total: int = 0


class MyPullsRead(BaseModel):
    # The GitHub login the list was asked for, or "" when none is configured.
    login: str = ""
    generated_at: UtcDateTime
    counts: dict[str, int] = {}
    # Why the list is empty, when GitHub could not be read or no login is set.
    error: str | None = None
    pulls: list[MyPullRead] = []
