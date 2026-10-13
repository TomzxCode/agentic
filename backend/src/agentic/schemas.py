"""Pydantic request/response models for the HTTP API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from .models import (
    AgentRun,
    Harness,
    Repository,
    SourceItem,
    Task,
    TaskStatus,
    TimelineEvent,
    Worktree,
)


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class SessionLink(BaseModel):
    """A way to open an agent session: a URL and/or a copyable command."""

    id: str  # openchamber | terminal | command
    label: str
    url: str | None = None
    command: str | None = None


class SettingsRead(BaseModel):
    effective: dict[str, str]
    overrides: dict[str, str]
    defaults: dict[str, str]


class SettingsUpdate(BaseModel):
    openchamber_url: str | None = None
    openchamber_session_path: str | None = None
    terminal_url_template: str | None = None
    editor_url_template: str | None = None


# --- Filesystem (repository picker) ---------------------------------------
class FsEntry(BaseModel):
    name: str
    path: str
    is_git: bool = False


class FsListing(BaseModel):
    root: str
    path: str
    parent: str | None = None
    is_git: bool = False
    entries: list[FsEntry] = []


# --- GitHub ----------------------------------------------------------------
class GithubIssue(BaseModel):
    number: int
    title: str = ""
    url: str = ""
    state: str = ""
    author: str | None = None
    labels: list[str] = []
    body: str = ""


# --- Repository ------------------------------------------------------------
class RepositoryCreate(BaseModel):
    name: str | None = None
    path: str
    remote_url: str | None = None
    default_branch: str | None = None


class RepositoryBulkCreate(BaseModel):
    paths: list[str]


class RepositoryRead(ORMModel):
    id: str
    name: str
    path: str
    remote_url: str | None = None
    default_branch: str | None = None
    created_at: datetime


class RepositoryBulkResult(BaseModel):
    added: list[RepositoryRead] = []
    errors: list[dict[str, str]] = []


# --- Repository groups -----------------------------------------------------
class RepositoryGroupCreate(BaseModel):
    name: str
    description: str = ""
    repository_ids: list[str] = []


class RepositoryGroupUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    repository_ids: list[str] | None = None


class RepositoryGroupRead(ORMModel):
    id: str
    name: str
    description: str
    repository_ids: list[str] = []
    created_at: datetime


# --- Harness ---------------------------------------------------------------
class HarnessCreate(BaseModel):
    name: str
    description: str = ""
    command: str
    args: list[str] = []
    env: dict[str, str] = {}
    model: str | None = None
    resume_command: str | None = None
    is_default: bool = False


class HarnessUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    command: str | None = None
    args: list[str] | None = None
    env: dict[str, str] | None = None
    model: str | None = None
    resume_command: str | None = None
    is_default: bool | None = None


class HarnessRead(ORMModel):
    id: str
    name: str
    description: str
    command: str
    args: list[str]
    env: dict[str, str]
    model: str | None = None
    resume_command: str | None = None
    is_default: bool


class HarnessStatus(BaseModel):
    id: str
    name: str
    available: bool
    detail: str = ""
    is_default: bool = False
    model: str | None = None


# --- SourceItem ------------------------------------------------------------
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
    url: str | None = None
    external_id: str | None = None
    metadata_json: dict[str, Any]
    content: str
    fetched_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    task_ids: list[str] = []
    person_ids: list[str] = []


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


# --- Task ---------------------------------------------------------------
class TaskCreate(BaseModel):
    title: str = ""
    description: str = ""
    status: TaskStatus = TaskStatus.open
    priority: int = 2
    tags: list[str] = []
    repository_ids: list[str] = []
    group_id: str | None = None
    harness_id: str | None = None
    # Import: create the task from a GitHub issue/PR (prefills title/description
    # and associates the issue as an item).
    github_url: str | None = None
    # Import: create the task from a Slack thread. Slackx gathers the
    # conversation and an agent then names the task and summarizes it.
    slack_url: str | None = None


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: TaskStatus | None = None
    priority: int | None = None
    tags: list[str] | None = None
    repository_ids: list[str] | None = None
    group_id: str | None = None
    harness_id: str | None = None
    summary: str | None = None
    next_steps: list[dict[str, Any]] | None = None


class TaskBulkUpdate(BaseModel):
    """Apply one status and/or tag edit to many tasks at once."""

    ids: list[str]
    status: TaskStatus | None = None
    add_tags: list[str] = []
    remove_tags: list[str] = []


class TaskRead(ORMModel):
    id: str
    title: str
    description: str
    status: TaskStatus
    priority: int
    tags: list[str]
    repository_ids: list[str] = []
    group_id: str | None = None
    harness_id: str | None = None
    summary: str
    next_steps: list[dict[str, Any]]
    context_updated_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class TaskBulkResult(BaseModel):
    """The tasks a bulk edit matched, plus any ids that no longer exist."""

    updated: list[TaskRead] = []
    missing: list[str] = []


class WorktreeRead(ORMModel):
    id: str
    task_id: str
    repository_id: str
    branch: str
    path: str
    status: str
    created_at: datetime
    removed_at: datetime | None = None


class RunRead(ORMModel):
    id: str
    task_id: str
    harness_id: str | None = None
    cwd: str | None = None
    worktree_id: str | None = None
    prompt: str
    kind: str
    status: str
    session_id: str | None = None
    stop_reason: str | None = None
    error: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    ended_at: datetime | None = None
    links: list[SessionLink] = []


class TimelineRead(ORMModel):
    id: str
    task_id: str
    type: str
    message: str
    data_json: dict[str, Any]
    client: str
    actor: str
    created_at: datetime


class TaskDetail(TaskRead):
    associations: list[AssociationDetail] = []
    people: list[PersonRead] = []
    worktrees: list[WorktreeRead] = []
    runs: list[RunRead] = []
    changes: list[ChangeRead] = []
    timeline: list[TimelineRead] = []


class OperationRead(ORMModel):
    """One row of the operations audit log."""

    id: str
    method: str
    path: str
    status_code: int
    client: str
    actor: str
    created_at: datetime


# --- People ----------------------------------------------------------------
class PersonCreate(BaseModel):
    name: str = ""
    email: str | None = None
    handle: str | None = None
    notes: str = ""


class PersonUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    handle: str | None = None
    notes: str | None = None


class PersonRead(ORMModel):
    id: str
    name: str
    email: str | None = None
    handle: str | None = None
    notes: str
    created_at: datetime
    updated_at: datetime
    task_count: int = 0
    item_count: int = 0


class PersonDetail(PersonRead):
    task_ids: list[str] = []
    item_ids: list[str] = []


class PersonLink(BaseModel):
    """Link an existing person (``person_id``) or create and link a new one (``name``)."""

    person_id: str | None = None
    name: str = ""


# --- Tags ------------------------------------------------------------------
class TagRead(BaseModel):
    """A tag in use, with how many tasks carry it."""

    name: str
    count: int


# --- Changes (factory metrics) ---------------------------------------------
class ChangeCreate(BaseModel):
    task_id: str
    title: str = ""
    change_class: str = "feature"
    repository_id: str | None = None
    worktree_id: str | None = None
    external_ref: str | None = None
    notes: str = ""
    human_intervened: bool = False
    opened_at: datetime | None = None


class ChangeUpdate(BaseModel):
    title: str | None = None
    change_class: str | None = None
    repository_id: str | None = None
    worktree_id: str | None = None
    external_ref: str | None = None
    notes: str | None = None


class ChangeStatusUpdate(BaseModel):
    status: str


class InterventionCreate(BaseModel):
    kind: str = "other"
    note: str = ""


class InterventionRead(ORMModel):
    id: str
    change_id: str
    kind: str
    note: str
    created_at: datetime


class ChangeRead(ORMModel):
    id: str
    task_id: str
    title: str
    change_class: str
    status: str
    repository_id: str | None = None
    worktree_id: str | None = None
    external_ref: str | None = None
    human_intervened: bool
    intervention_count: int
    opened_at: datetime
    verified_at: datetime | None = None
    accepted_at: datetime | None = None
    closed_at: datetime | None = None
    notes: str
    created_at: datetime
    updated_at: datetime


class ChangeDetail(ChangeRead):
    interventions: list[InterventionRead] = []


class MetricCounts(BaseModel):
    accepted: int = 0
    touchless: int = 0
    reverted: int = 0
    rejected: int = 0
    pending_observation: int = 0
    open: int = 0


class MetricResult(BaseModel):
    metric: str
    label: str
    value: float | None = None
    numerator: int = 0
    denominator: int = 0
    baseline: float | None = None
    delta: float | None = None
    direction: str
    unit: str = "ratio"


class MetricsReport(BaseModel):
    window_days: int
    observation_days: int
    tolerance: float
    generated_at: datetime
    metrics: list[MetricResult] = []
    counts: MetricCounts = MetricCounts()


class BaselineSet(BaseModel):
    value: float
    window_days: int = 30
    observation_days: int = 14
    note: str = ""
    captured_at: datetime | None = None


class BaselineRead(ORMModel):
    metric: str
    value: float
    window_days: int
    observation_days: int
    note: str
    captured_at: datetime


# --- Gantt -----------------------------------------------------------------
class GanttTask(BaseModel):
    """A task as a Gantt row: its span, plus one marker per timeline event."""

    id: str
    title: str
    status: TaskStatus
    priority: int
    created_at: datetime
    updated_at: datetime
    markers: list[TimelineRead] = []


# --- Worktree --------------------------------------------------------------
class WorktreeCreate(BaseModel):
    repository_id: str | None = None
    branch: str | None = None
    base: str | None = None


# --- Agent runs ------------------------------------------------------------
class RunCreate(BaseModel):
    prompt: str
    harness_id: str | None = None
    worktree_id: str | None = None
    cwd: str | None = None


class AgentEventRead(ORMModel):
    id: int | None = None
    run_id: str
    seq: int
    type: str
    text: str
    data_json: dict[str, Any]
    created_at: datetime


class ContextPreview(BaseModel):
    task_id: str
    summary: str
    next_steps: list[dict[str, Any]]
    context_updated_at: datetime | None = None


__all__ = [
    "AgentEventRead",
    "AgentRun",
    "AssociateRequest",
    "AssociationDetail",
    "AssociationRead",
    "BaselineRead",
    "BaselineSet",
    "ChangeCreate",
    "ChangeDetail",
    "ChangeRead",
    "ChangeStatusUpdate",
    "ChangeUpdate",
    "ContextPreview",
    "FsEntry",
    "FsListing",
    "GanttTask",
    "GithubIssue",
    "Harness",
    "HarnessCreate",
    "HarnessRead",
    "HarnessStatus",
    "HarnessUpdate",
    "InterventionCreate",
    "InterventionRead",
    "ItemCreate",
    "ItemRead",
    "ItemUpdate",
    "MetricCounts",
    "MetricResult",
    "MetricsReport",
    "OperationRead",
    "PersonCreate",
    "PersonDetail",
    "PersonLink",
    "PersonRead",
    "PersonUpdate",
    "Task",
    "TaskBulkResult",
    "TaskBulkUpdate",
    "TaskCreate",
    "TaskDetail",
    "TaskRead",
    "TaskUpdate",
    "Repository",
    "RepositoryBulkCreate",
    "RepositoryBulkResult",
    "RepositoryCreate",
    "RepositoryGroupCreate",
    "RepositoryGroupRead",
    "RepositoryGroupUpdate",
    "RepositoryRead",
    "RunCreate",
    "RunRead",
    "SessionLink",
    "SettingsRead",
    "SettingsUpdate",
    "SourceItem",
    "TimelineEvent",
    "TimelineRead",
    "Worktree",
    "WorktreeCreate",
    "WorktreeRead",
]

# TaskDetail references ChangeRead defined later in this module; resolve it now.
TaskDetail.model_rebuild()
