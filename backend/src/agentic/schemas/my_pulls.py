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
    # Whether anyone but the author has submitted a review (a comment counts),
    # and who GitHub still lists as requested reviewers.
    reviewed: bool = False
    requested_reviewers: list[str] = []


class MyPullsRead(BaseModel):
    # The GitHub login the list was asked for, or "" when none is configured.
    login: str = ""
    generated_at: UtcDateTime
    counts: dict[str, int] = {}
    # Why the list is empty, when GitHub could not be read or no login is set.
    error: str | None = None
    pulls: list[MyPullRead] = []


class MyPullCheck(BaseModel):
    """One check run or commit status behind a pull request's CI badge."""

    name: str
    # failure / pending / success, the same vocabulary as the rollup.
    state: str = "pending"
    # What the check reported, or a short label when it names no description.
    description: str = ""
    # The check's detail page on GitHub, when it has one.
    url: str = ""


class MyPullChecksRead(BaseModel):
    """The checks behind one pull request, failing first."""

    repository: str
    number: int
    # The head commit's rollup, so the popover agrees with the badge.
    rollup: str = "none"
    checks: list[MyPullCheck] = []
    # Every check on the commit, which can exceed the listed ones.
    total: int = 0
    # Why the checks are missing, when GitHub could not be read.
    error: str | None = None


class MyPullPokeRequest(BaseModel):
    """Ask the API to DM a pull request's reviewers on Slack.

    The pull request is named by its fields rather than by a tracked item, so a
    pull request the app does not track can still be poked; ``logins`` is the
    requested reviewers the My PRs read carried.
    """

    repository: str
    number: int
    title: str = ""
    url: str = ""
    logins: list[str] = []


class MyPullPokeSent(BaseModel):
    """One reviewer the poke reached."""

    login: str
    name: str = ""
    slack_user_id: str
    ts: str | None = None


class MyPullPokeFailure(BaseModel):
    """One reviewer the poke could not reach, and why."""

    login: str
    reason: str


class MyPullPokeRead(BaseModel):
    """The outcome of poking a pull request's reviewers."""

    poked: list[MyPullPokeSent] = []
    failed: list[MyPullPokeFailure] = []
