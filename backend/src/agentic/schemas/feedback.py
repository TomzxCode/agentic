"""PR-feedback triage models.

The reviewer-feedback analysis files live outside the database, in the
user-global ``~/.sdlc`` store. These models are the shape the PR-feedback view
reads and the decision it writes, with the two derived fields (``status`` and
``run_state``) that drive its colours and filters.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from .base import UtcDateTime

#: A recorded decision. ``None`` resets the item to awaiting a decision.
Decision = Literal["implement", "decline", "defer"]


class FeedbackItemRead(BaseModel):
    feedback_id: str
    kind: str
    repo: str
    pr: str
    author: str
    created_at: str
    head_commit: str
    analyzed_at: str
    recommendation: str
    confidence: str
    session_link: str
    decision: str | None = None
    decided_at: str | None = None
    executed_at: str | None = None
    title: str
    # The analysis file's path in the store, so the view can offer to open it in
    # an editor. It is outside the served tree, so the web UI only copies it.
    path: str
    # The file's named sections ("Comment", "Analysis", …) as raw Markdown.
    sections: dict[str, str] = {}
    # The decision, or "pending"; the view's status pill and filter.
    status: str
    # "executed", "awaiting", or "none"; whether the decision has been run.
    run_state: str
    # The pull request's GitHub state ("open"/"closed"), or "" when unknown
    # (ghx unavailable, or a store key with no owner).
    state: str = ""
    pr_url: str = ""


class FeedbackListRead(BaseModel):
    # The store root that was scanned, or None when it does not exist.
    root: str | None = None
    generated_at: UtcDateTime
    counts: dict[str, int] = {}
    items: list[FeedbackItemRead] = []


class FeedbackDecisionUpdate(BaseModel):
    decision: Decision | None = None
