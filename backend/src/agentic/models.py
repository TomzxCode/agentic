"""SQLModel tables for the Agentic app.

The core idea: work is organized around *tasks*. Anything external (a Slack
thread, a GitHub issue, a Drive doc, a URL, a note, a commit) becomes a
``SourceItem`` that can be associated to one or more tasks. Worktrees and
agent runs also hang off a task, and every meaningful change writes a
``TimelineEvent`` so a task's evolution is visible at a glance.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, SQLModel


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


class Repository(SQLModel, table=True):
    """A local git checkout that tasks can create worktrees from."""

    id: str = Field(default_factory=new_id, primary_key=True)
    name: str
    path: str
    remote_url: str | None = None
    default_branch: str | None = None
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

    # Agent-maintained context. This is what makes coming back to a task fast.
    summary: str = ""
    next_steps: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    context_updated_at: datetime | None = None

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


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


class SourceItem(SQLModel, table=True):
    """Something external that can be associated to tasks."""

    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_source_external_id"),)

    id: str = Field(default_factory=new_id, primary_key=True)
    source: str  # slack | github | gdrive | url | note | commit | file
    kind: str = ""  # thread | issue | pr | doc | ...
    title: str = ""
    url: str | None = None
    external_id: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    content: str = ""  # pulled text (thread transcript, issue body, doc text)
    fetched_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Association(SQLModel, table=True):
    """Links a SourceItem to a Task (many-to-many) with provenance."""

    id: str = Field(default_factory=new_id, primary_key=True)
    task_id: str = Field(foreign_key="task.id", index=True)
    item_id: str = Field(foreign_key="sourceitem.id", index=True)
    note: str = ""
    created_at: datetime = Field(default_factory=utcnow)


class Person(SQLModel, table=True):
    """An individual a task or a source item involves.

    People are a flat directory: a name plus a set of aliases. They link to
    tasks and items many-to-many through the ``taskperson`` and ``itemperson``
    join tables, so the same person can be seen from either side.
    """

    id: str = Field(default_factory=new_id, primary_key=True)
    name: str
    notes: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class PersonAlias(SQLModel, table=True):
    """An identifier for a person: a handle (GitHub login, Slack user id) or an email.

    A person carries many aliases in one flat list; the value is the identity
    used to de-duplicate people across sources, so a handle and an email are the
    same concept here (an identifier string).
    """

    __table_args__ = (UniqueConstraint("person_id", "value", name="uq_person_alias"),)

    id: str = Field(default_factory=new_id, primary_key=True)
    person_id: str = Field(foreign_key="person.id", index=True)
    value: str = Field(index=True)
    created_at: datetime = Field(default_factory=utcnow)


class TaskPerson(SQLModel, table=True):
    """Associates a task with 0..n people it involves."""

    __table_args__ = (UniqueConstraint("task_id", "person_id", name="uq_task_person"),)

    id: str = Field(default_factory=new_id, primary_key=True)
    task_id: str = Field(foreign_key="task.id", index=True)
    person_id: str = Field(foreign_key="person.id", index=True)
    created_at: datetime = Field(default_factory=utcnow)


class ItemPerson(SQLModel, table=True):
    """Associates a source item with 0..n people behind it."""

    __table_args__ = (UniqueConstraint("item_id", "person_id", name="uq_item_person"),)

    id: str = Field(default_factory=new_id, primary_key=True)
    item_id: str = Field(foreign_key="sourceitem.id", index=True)
    person_id: str = Field(foreign_key="person.id", index=True)
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


class Harness(SQLModel, table=True):
    """A coding-agent harness reachable over ACP (opencode, pi, ...)."""

    id: str = Field(default_factory=new_id, primary_key=True)
    name: str
    description: str = ""
    command: str
    args: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    env: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON))
    model: str | None = None
    # Template for resuming a session in a terminal, e.g.
    # "opencode --session {session}". Placeholders: {session} {cwd} {harness}.
    resume_command: str | None = None
    is_default: bool = False
    created_at: datetime = Field(default_factory=utcnow)


class Setting(SQLModel, table=True):
    """Key/value app settings that override environment defaults."""

    key: str = Field(primary_key=True)
    value: str = ""
    updated_at: datetime = Field(default_factory=utcnow)


class AgentRun(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    task_id: str = Field(foreign_key="task.id", index=True)
    harness_id: str | None = Field(default=None, foreign_key="harness.id")
    cwd: str | None = None
    worktree_id: str | None = Field(default=None, foreign_key="worktree.id")
    prompt: str = ""
    kind: str = "chat"  # chat | refresh_context
    status: RunStatus = RunStatus.queued
    session_id: str | None = None  # ACP session id
    stop_reason: str | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    started_at: datetime | None = None
    ended_at: datetime | None = None


class AgentEvent(SQLModel, table=True):
    """A single normalized event in an agent run's transcript."""

    id: int | None = Field(default=None, primary_key=True)
    run_id: str = Field(foreign_key="agentrun.id", index=True)
    seq: int = 0
    type: str = "info"  # message | thought | tool_call | tool_update | plan | usage | status | error
    text: str = ""
    data_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)


class TimelineEvent(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    task_id: str = Field(foreign_key="task.id", index=True)
    type: str
    message: str = ""
    data_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    client: OperationClient = Field(default=OperationClient.api)
    actor: OperationActor = Field(default=OperationActor.human)
    created_at: datetime = Field(default_factory=utcnow)


class Operation(SQLModel, table=True):
    """One mutating request, kept as an audit log of how work entered the system.

    Records the method and path, the resulting status, which client sent it, and
    whether a person or a coding agent was behind it. This is the cross-cutting
    counterpart to a task's timeline: it covers operations with no task to hang a
    ``TimelineEvent`` off, such as settings, repositories, and harnesses.
    """

    id: str = Field(default_factory=new_id, primary_key=True)
    method: str = ""
    path: str = ""
    status_code: int = 0
    client: OperationClient = Field(default=OperationClient.api, index=True)
    actor: OperationActor = Field(default=OperationActor.human, index=True)
    created_at: datetime = Field(default_factory=utcnow)


class Change(SQLModel, table=True):
    """One unit of factory output, instrumented for the autonomy and yield metrics.

    A change carries an id, a start (``opened_at``), an end (``accepted_at`` or
    ``closed_at``), and a human-intervened flag, which is everything the metric
    engine needs. It lives between the task that owns it and the interventions
    recorded against it.
    """

    id: str = Field(default_factory=new_id, primary_key=True)
    task_id: str = Field(foreign_key="task.id", index=True)
    title: str = ""
    change_class: ChangeClass = ChangeClass.feature
    status: ChangeStatus = Field(default=ChangeStatus.proposed, index=True)
    repository_id: str | None = Field(default=None, foreign_key="repository.id")
    worktree_id: str | None = Field(default=None, foreign_key="worktree.id")
    external_ref: str | None = None
    human_intervened: bool = False
    intervention_count: int = 0
    opened_at: datetime = Field(default_factory=utcnow)
    verified_at: datetime | None = None
    accepted_at: datetime | None = Field(default=None, index=True)
    closed_at: datetime | None = None
    notes: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class ChangeIntervention(SQLModel, table=True):
    """A recorded human touch on a change: a question, correction, fix, rerun, or approval."""

    id: str = Field(default_factory=new_id, primary_key=True)
    change_id: str = Field(foreign_key="change.id", index=True)
    kind: InterventionKind = InterventionKind.other
    note: str = ""
    created_at: datetime = Field(default_factory=utcnow)


class MetricBaseline(SQLModel, table=True):
    """The comparison point a metric's direction is measured against.

    One row per metric; the article's advice to write the baseline down before
    the first factory run only means something if the value is stored.
    """

    metric: str = Field(primary_key=True)
    value: float
    window_days: int = 30
    observation_days: int = 14
    note: str = ""
    captured_at: datetime = Field(default_factory=utcnow)
