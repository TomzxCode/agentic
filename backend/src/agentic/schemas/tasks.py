"""Pydantic request/response models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from ..models.base import DependencyRelation, TaskStatus
from .base import ORMModel, UtcDateTime
from .changes import ChangeRead
from .checklists import ChecklistItemRead
from .items import AssociationDetail
from .people import PersonRead
from .runs import RunRead, SessionRead


class TaskCreate(BaseModel):
    title: str = ""
    description: str = ""
    status: TaskStatus = TaskStatus.open
    priority: int = 2
    tags: list[str] = []
    deadline: UtcDateTime | None = None
    waiting_on_person_id: str | None = None
    follow_up_at: UtcDateTime | None = None
    snoozed_until: UtcDateTime | None = None
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
    deadline: UtcDateTime | None = None
    waiting_on_person_id: str | None = None
    follow_up_at: UtcDateTime | None = None
    snoozed_until: UtcDateTime | None = None
    repository_ids: list[str] | None = None
    group_id: str | None = None
    harness_id: str | None = None
    summary: str | None = None
    next_steps: list[dict[str, Any]] | None = None


class TaskBulkUpdate(BaseModel):
    """Apply one status, priority, and/or tag edit to many tasks at once."""

    ids: list[str]
    status: TaskStatus | None = None
    priority: int | None = None
    add_tags: list[str] = []
    remove_tags: list[str] = []


class TaskBulkDelete(BaseModel):
    """Delete many tasks at once."""

    ids: list[str]


class TaskBulkDeleteResult(BaseModel):
    """The task ids a bulk delete removed, plus any ids that no longer exist."""

    deleted: list[str] = []
    missing: list[str] = []


class TaskRead(ORMModel):
    id: str
    title: str
    description: str
    status: TaskStatus
    priority: int
    tags: list[str]
    deadline: datetime | None = None
    waiting_on_person_id: str | None = None
    # The waiting person's name, resolved for display (the id alone would make
    # every reader do its own people lookup).
    waiting_on_name: str | None = None
    follow_up_at: datetime | None = None
    snoozed_until: datetime | None = None
    repository_ids: list[str] = []
    person_ids: list[str] = []
    requester_ids: list[str] = []
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
    # People who asked for the task, a link set separate from the people it
    # involves; the same person can appear in either or both.
    requesters: list[PersonRead] = []
    # People named by the task's items (an issue/PR author, a commenter) that
    # are not yet linked to the task, offered as one-click links in the UI.
    suggested_people: list[PersonRead] = []
    worktrees: list[WorktreeRead] = []
    runs: list[RunRead] = []
    sessions: list[SessionRead] = []
    changes: list[ChangeRead] = []
    checklist: list[ChecklistItemRead] = []
    timeline: list[TimelineRead] = []


class DependencyCreate(BaseModel):
    """Link ``related_id`` to the task: before it, after it, or as a related task."""

    related_id: str
    relation: DependencyRelation = DependencyRelation.after


class TaskDependencies(BaseModel):
    """A task's linked neighbours, resolved to full tasks.

    ``before``/``after`` are the ordered sides of the dependency graph;
    ``related`` is the symmetric pair list, which reads the same from both tasks.
    """

    task_id: str
    before: list[TaskRead] = []
    after: list[TaskRead] = []
    related: list[TaskRead] = []


class GraphNode(BaseModel):
    """A task as a node in the before/after graph."""

    id: str
    title: str
    status: TaskStatus
    priority: int


class GraphEdge(BaseModel):
    """A directed edge: ``before_id`` must be done before ``after_id``."""

    before_id: str
    after_id: str


class DependencyGraph(BaseModel):
    """The whole before/after graph: the tasks and the edges between them."""

    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []


# TaskDetail references classes defined in sibling modules; resolve now.
TaskDetail.model_rebuild()
