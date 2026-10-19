"""SQLModel tables for repositories."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

from .base import (
    WorktreeStatus,
    new_id,
    utcnow,
)


class ReviewScanPolicy(StrEnum):
    """Whether the review scan considers a repository's pull requests.

    ``default`` follows the app-wide setting, so a repository only needs an
    opinion when it differs from every other one.
    """

    default = "default"
    include = "include"
    exclude = "exclude"


class Repository(SQLModel, table=True):
    """A local git checkout that tasks can create worktrees from."""

    id: str = Field(default_factory=new_id, primary_key=True)
    name: str
    path: str
    remote_url: str | None = None
    default_branch: str | None = None
    # One of ReviewScanPolicy: whether the pull requests of this repository are
    # part of the review scan.
    review_scan: str = ReviewScanPolicy.default.value
    created_at: datetime = Field(default_factory=utcnow)


class RepositoryGroup(SQLModel, table=True):
    """A named set of repositories that a task's agent should consider.

    Groups tell the agent which checkouts may contain information relevant to a
    task, without the user having to spell it out in each prompt.
    """

    id: str = Field(default_factory=new_id, primary_key=True)
    name: str
    description: str = ""
    created_at: datetime = Field(default_factory=utcnow)


class RepositoryGroupMember(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("group_id", "repository_id", name="uq_group_repository"),)

    id: str = Field(default_factory=new_id, primary_key=True)
    group_id: str = Field(foreign_key="repositorygroup.id", index=True)
    repository_id: str = Field(foreign_key="repository.id", index=True)
    created_at: datetime = Field(default_factory=utcnow)


class TaskRepository(SQLModel, table=True):
    """Associates a task with 0..n repositories it may draw on."""

    __table_args__ = (UniqueConstraint("task_id", "repository_id", name="uq_task_repository"),)

    id: str = Field(default_factory=new_id, primary_key=True)
    task_id: str = Field(foreign_key="task.id", index=True)
    repository_id: str = Field(foreign_key="repository.id", index=True)
    created_at: datetime = Field(default_factory=utcnow)


class Worktree(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    task_id: str = Field(foreign_key="task.id", index=True)
    repository_id: str = Field(foreign_key="repository.id")
    branch: str
    path: str
    status: WorktreeStatus = WorktreeStatus.active
    created_at: datetime = Field(default_factory=utcnow)
    removed_at: datetime | None = None
