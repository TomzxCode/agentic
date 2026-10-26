"""SQLModel tables for tasks."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, SQLModel

from .base import (
    OperationActor,
    OperationClient,
    TaskStatus,
    new_id,
    utcnow,
)


class Task(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    title: str
    description: str = ""
    status: TaskStatus = TaskStatus.open
    priority: int = 2  # 0 = low, 1 = medium, 2 = high, 3 = urgent
    tags: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    group_id: str | None = Field(default=None, foreign_key="repositorygroup.id")
    harness_id: str | None = Field(default=None, foreign_key="harness.id")
    # When the task should be done by; None means no deadline is set.
    deadline: datetime | None = None
    # Who the task is waiting on, and when to check back. A task with a waiting
    # person parks off the focus stack until the follow-up date (or until the
    # person is cleared); with no follow-up it stays parked.
    waiting_on_person_id: str | None = Field(default=None, foreign_key="person.id")
    follow_up_at: datetime | None = None
    # When the task comes back off its snooze and rejoins the stack. A snooze in
    # the past has no effect; the task is simply visible again.
    snoozed_until: datetime | None = None

    # Agent-maintained context. This is what makes coming back to a task fast.
    summary: str = ""
    next_steps: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    context_updated_at: datetime | None = None

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class TaskDependency(SQLModel, table=True):
    """A directed before/after link between two tasks.

    ``before_id`` must be done before ``after_id``, so an edge points from the
    earlier task to the later one. The pair is unique, and the graph the edges
    form is kept acyclic: adding an edge that would close a cycle is refused.
    """

    __table_args__ = (UniqueConstraint("before_id", "after_id", name="uq_dependency_edge"),)

    id: str = Field(default_factory=new_id, primary_key=True)
    before_id: str = Field(foreign_key="task.id", index=True)
    after_id: str = Field(foreign_key="task.id", index=True)
    created_at: datetime = Field(default_factory=utcnow)


class TaskRelation(SQLModel, table=True):
    """A symmetric "related" link between two tasks.

    The pair is stored once with the two ids ordered, so the link reads the same
    from either task and a second link between the pair is refused as a
    duplicate. It is not an ordering statement, so it never joins the
    before/after graph.
    """

    __table_args__ = (UniqueConstraint("task_id", "related_id", name="uq_related_pair"),)

    id: str = Field(default_factory=new_id, primary_key=True)
    task_id: str = Field(foreign_key="task.id", index=True)
    related_id: str = Field(foreign_key="task.id", index=True)
    created_at: datetime = Field(default_factory=utcnow)


class StackEntry(SQLModel, table=True):
    """One task's place on the focus stack.

    The stack is an ordered list of tasks where position 0 is the current task
    and the rest are queued. Popping or removing an entry soft-deletes it
    (``deleted_at``) so the stack keeps a history of what was worked on.
    """

    id: str = Field(default_factory=new_id, primary_key=True)
    task_id: str = Field(foreign_key="task.id", index=True)
    position: int = Field(default=0, index=True)
    is_current: bool = False
    created_at: datetime = Field(default_factory=utcnow)
    deleted_at: datetime | None = None
    # Why the entry left the stack: popped, removed, or parked. A parked entry
    # rejoins when its task's snooze or waiting follow-up date passes, which is
    # how a deferral returns to the stack without being pushed by hand.
    deleted_reason: str | None = None


class TaskSession(SQLModel, table=True):
    """A stretch of time a stack entry spent as the current task.

    A session opens when an entry becomes current and closes when it stops
    being current. An entry's ``execution_count`` and ``duration`` are derived
    from these rows.
    """

    id: str = Field(default_factory=new_id, primary_key=True)
    stack_entry_id: str = Field(foreign_key="stackentry.id", index=True)
    started_at: datetime = Field(default_factory=utcnow)
    ended_at: datetime | None = None


class TimelineEvent(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    task_id: str = Field(foreign_key="task.id", index=True)
    type: str
    message: str = ""
    data_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    client: OperationClient = Field(default=OperationClient.api)
    actor: OperationActor = Field(default=OperationActor.human)
    created_at: datetime = Field(default_factory=utcnow)
