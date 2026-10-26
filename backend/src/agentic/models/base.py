"""Shared model primitives: ids, timestamps, and enum values."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def utcnow() -> datetime:
    return datetime.now(UTC)


class TaskStatus(StrEnum):
    open = "open"
    in_progress = "in_progress"
    blocked = "blocked"
    done = "done"
    archived = "archived"


class DependencyRelation(StrEnum):
    """How a related task is linked to this one.

    ``before`` and ``after`` place it on a side of the ordering graph;
    ``related`` is a symmetric link, with no direction.
    """

    before = "before"
    after = "after"
    related = "related"


class RunStatus(StrEnum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class WorktreeStatus(StrEnum):
    active = "active"
    removed = "removed"


class ChangeStatus(StrEnum):
    proposed = "proposed"
    verified = "verified"
    accepted = "accepted"
    rejected = "rejected"
    reverted = "reverted"


class ChangeClass(StrEnum):
    feature = "feature"
    bugfix = "bugfix"
    refactor = "refactor"
    chore = "chore"
    docs = "docs"
    test = "test"
    trivial = "trivial"


class InterventionKind(StrEnum):
    question = "question"
    correction = "correction"
    manual_fix = "manual_fix"
    rerun = "rerun"
    approval = "approval"
    other = "other"


class OperationClient(StrEnum):
    """Which client sent a request: the web UI, the CLI, or the raw API."""

    web = "web"
    cli = "cli"
    api = "api"


class OperationActor(StrEnum):
    """Who is behind a request: a person or a coding agent."""

    human = "human"
    agent = "agent"


class ScheduledRunStatus(StrEnum):
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class GraphExecutionStatus(StrEnum):
    """The state of one run of an execution graph."""

    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"
