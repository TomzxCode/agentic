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
    created_at: datetime


class TaskDetail(TaskRead):
    associations: list[AssociationDetail] = []
    worktrees: list[WorktreeRead] = []
    runs: list[RunRead] = []
    timeline: list[TimelineRead] = []


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
    "ItemCreate",
    "ItemRead",
    "ItemUpdate",
    "Task",
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
