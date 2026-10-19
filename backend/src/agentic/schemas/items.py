"""Pydantic request/response models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from .base import ORMModel


class ItemCreate(BaseModel):
    source: str | None = None  # inferred from url/content when omitted
    kind: str = ""
    title: str = ""
    url: str | None = None
    external_id: str | None = None
    content: str = ""
    metadata_json: dict[str, Any] = {}
    fetch: bool = True


class ItemUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    kind: str | None = None
    metadata_json: dict[str, Any] | None = None


class ItemRead(ORMModel):
    id: str
    source: str
    kind: str
    title: str
    # True when a person set the title; a refresh leaves such a title alone.
    title_custom: bool = False
    url: str | None = None
    external_id: str | None = None
    metadata_json: dict[str, Any]
    content: str
    fetched_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    task_ids: list[str] = []
    person_ids: list[str] = []
    # Set on a single-item response (create or refresh) when the fetch could not
    # run, so the UI can show the failure instead of reading empty data as success.
    fetch_error: str | None = None


class ItemReviewFile(BaseModel):
    """One Markdown report in a PR's user-global review directory.

    ``skill`` and ``commit`` come from the ``<skill>.<short-sha>.md`` name, so
    the UI can group the reports of one reviewed commit together; both are None
    for a file without a commit in its name (a raw cache, a "no-issue" variant).
    """

    name: str
    skill: str | None = None
    commit: str | None = None
    size: int
    modified_at: datetime


class ItemReviews(BaseModel):
    """The review reports a GitHub pull request item has on disk.

    ``path`` is the resolved directory (None when the PR has no report
    directory); ``files`` is empty when there is nothing to show.
    """

    path: str | None = None
    files: list[ItemReviewFile] = []


class ItemReviewContent(BaseModel):
    """The content of one review report."""

    name: str
    content: str
    truncated: bool = False


class ReviewStepRead(BaseModel):
    """One review step's newest report for a pull request."""

    step: str
    commit: str = ""
    verdict: str = ""
    risk: str = ""
    confidence: str = ""
    stale: bool = False
    report: str | None = None
    modified_at: datetime | None = None


class ReviewFindingRead(BaseModel):
    """One must/should/may finding a review skill recorded for a pull request.

    ``step`` is the skill that recorded it, ``severity`` is one of must, should,
    or may, and ``status`` is the skill's own status for the finding (open,
    addressed, conforms, ...). ``sha`` is the commit the finding was first seen
    at, informational only. ``decision`` is the reviewer's own choice about
    forwarding it (``include`` or ``skip``), empty until one is recorded, and
    ``decided_at`` is when that choice was made.
    """

    step: str
    title: str
    description: str = ""
    severity: str
    status: str = ""
    sha: str = ""
    decision: str = ""
    decided_at: str = ""


class ReviewFindingDecision(BaseModel):
    """The reviewer's decision on one finding, addressed by skill and title."""

    step: str
    title: str
    decision: str


class ReviewFindingsDecisions(BaseModel):
    """The decisions to record on one pull request's findings in one write."""

    repository: str
    decisions: list[ReviewFindingDecision] = []


class ReviewPrRead(BaseModel):
    """One pull request in the review queue, with its review-step state.

    ``head_commit`` is the newest commit any report covered, which stands in for
    the PR's head (the store holds no live GitHub read). ``created_at`` and
    ``last_comment_at`` are ISO strings parsed from the store's ``gh pr view``
    cache, so a value can be missing.
    """

    owner: str = ""
    name: str
    repository: str
    number: int
    title: str = ""
    url: str = ""
    author: str = ""
    state: str = ""
    draft: bool = False
    head_branch: str = ""
    base_branch: str = ""
    labels: list[str] = []
    created_at: str | None = None
    last_comment_at: str | None = None
    last_comment_by: str = ""
    head_commit: str = ""
    # When a review skill last wrote for this PR: the newest step report's
    # modification time. None when the store holds no step report.
    reviewed_at: datetime | None = None
    steps: dict[str, ReviewStepRead] = {}
    stale_steps: list[str] = []
    reviewed_steps: int = 0
    readiness: str = "yellow"
    status: str = "needs-review"
    item_id: str | None = None
    # The tasks the PR's tracked item is associated to (empty when it is
    # untracked or not yet linked), so the queue can link a PR to its task
    # instead of offering to import one.
    task_ids: list[str] = []
    # How the review scan found this PR: "requested" (a review is asked of you)
    # or "reviewed" (you reviewed it and it is still open). Empty for a PR that
    # is only in the report store.
    request_source: str = ""


class ReviewScanRead(BaseModel):
    """The review scan's configuration and its last pass."""

    interval: str = ""
    enabled: bool = False
    interval_seconds: float | None = None
    # What a repository with no policy of its own does: include or exclude.
    default: str = "include"
    # How many pull requests the scan currently holds.
    stored: int = 0
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
    # The last pass: what the searches returned, and what survived the filter.
    found: int = 0
    kept: int = 0
    error: str | None = None
    origin: str | None = None


class ReviewQueueRead(BaseModel):
    """Every pull request in the store with review reports, newest first."""

    root: str | None = None
    generated_at: datetime
    counts: dict[str, int] = {}
    prs: list[ReviewPrRead] = []


class AssociationRead(ORMModel):
    id: str
    task_id: str
    item_id: str
    note: str
    created_at: datetime


class AssociationDetail(BaseModel):
    id: str
    note: str
    created_at: datetime
    item: ItemRead


class AssociateRequest(BaseModel):
    item_id: str | None = None
    item: ItemCreate | None = None
    note: str = ""
