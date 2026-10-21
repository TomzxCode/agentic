"""Shared task helpers: read models, repository links, and item linking."""

from __future__ import annotations

from sqlalchemy import case
from sqlalchemy import delete as sa_delete
from sqlmodel import Session, col, select

from ..links import run_read, session_read
from ..models.agents import AgentRun, AgentSession
from ..models.base import WorktreeStatus
from ..models.changes import Change
from ..models.items import Association, Person, SourceItem, TaskPerson, TaskRequester
from ..models.repositories import Repository, TaskRepository, Worktree
from ..models.tasks import Task, TimelineEvent
from ..schemas.changes import ChangeRead
from ..schemas.items import AssociationDetail, ItemRead
from ..schemas.tasks import (
    TaskDetail,
    TaskRead,
    TimelineRead,
    WorktreeRead,
)
from ..services.github import github_owner_repo
from ..services.sources import fetch_source
from .people_links import link_item_people_to_task, link_people_to_item
from .people_service import (
    _person_read,
    item_person_ids,
    task_people,
    task_person_ids,
    task_requester_ids,
    task_requesters,
)


def _task_repository_ids(session: Session, task_id: str) -> list[str]:
    return [
        member.repository_id
        for member in session.exec(
            select(TaskRepository).where(TaskRepository.task_id == task_id).order_by(col(TaskRepository.created_at))
        ).all()
    ]


def _set_task_repositories(session: Session, task_id: str, repository_ids: list[str]) -> None:
    session.exec(sa_delete(TaskRepository).where(col(TaskRepository.task_id) == task_id))
    seen: set[str] = set()
    for repository_id in repository_ids:
        if repository_id in seen or session.get(Repository, repository_id) is None:
            continue
        seen.add(repository_id)
        session.add(TaskRepository(task_id=task_id, repository_id=repository_id))
    session.commit()


def _repository_for_item(session: Session, item: SourceItem) -> Repository | None:
    """The repository a source item belongs to, matched by its GitHub owner/repo.

    GitHub issue and PR links carry the repository they live in, so a task that
    tracks one can be pointed at the matching local checkout automatically.
    """
    if item.source != "github":
        return None
    target = github_owner_repo(item.url)
    if target is None:
        return None
    wanted = (target[0].lower(), target[1].lower())
    for repository in session.exec(select(Repository)).all():
        remote = github_owner_repo(repository.remote_url)
        if remote and (remote[0].lower(), remote[1].lower()) == wanted:
            return repository
    return None


def _link_repository_for_item(session: Session, task_id: str, item: SourceItem) -> Repository | None:
    """Attach the item's repository to the task (idempotent) when it matches one."""
    repository = _repository_for_item(session, item)
    if repository is None:
        return None
    existing = session.exec(
        select(TaskRepository).where(TaskRepository.task_id == task_id, TaskRepository.repository_id == repository.id)
    ).first()
    if existing is None:
        session.add(TaskRepository(task_id=task_id, repository_id=repository.id))
        session.commit()
    return repository


def _task_read(session: Session, task: Task) -> TaskRead:
    data = TaskRead.model_validate(task)
    data.repository_ids = _task_repository_ids(session, task.id)
    data.person_ids = task_person_ids(session, task.id)
    data.requester_ids = task_requester_ids(session, task.id)
    if task.waiting_on_person_id:
        person = session.get(Person, task.waiting_on_person_id)
        data.waiting_on_name = person.name if person is not None else None
    return data


def _task_reads(session: Session, tasks: list[Task]) -> list[TaskRead]:
    """Batched version of ``_task_read`` for lists, to avoid N+1 queries."""
    if not tasks:
        return []
    task_ids = [task.id for task in tasks]

    repository_ids_by_task: dict[str, list[str]] = {task_id: [] for task_id in task_ids}
    for member in session.exec(
        select(TaskRepository)
        .where(col(TaskRepository.task_id).in_(task_ids))
        .order_by(col(TaskRepository.created_at))
    ).all():
        repository_ids_by_task.setdefault(member.task_id, []).append(member.repository_id)

    person_ids_by_task: dict[str, list[str]] = {task_id: [] for task_id in task_ids}
    for link in session.exec(
        select(TaskPerson).where(col(TaskPerson.task_id).in_(task_ids)).order_by(col(TaskPerson.created_at))
    ).all():
        person_ids_by_task.setdefault(link.task_id, []).append(link.person_id)

    requester_ids_by_task: dict[str, list[str]] = {task_id: [] for task_id in task_ids}
    for link in session.exec(
        select(TaskRequester).where(col(TaskRequester.task_id).in_(task_ids)).order_by(col(TaskRequester.created_at))
    ).all():
        requester_ids_by_task.setdefault(link.task_id, []).append(link.person_id)

    waiting_ids = {task.waiting_on_person_id for task in tasks if task.waiting_on_person_id}
    waiting_people = {}
    if waiting_ids:
        for person in session.exec(select(Person).where(col(Person.id).in_(waiting_ids))).all():
            waiting_people[person.id] = person

    reads: list[TaskRead] = []
    for task in tasks:
        data = TaskRead.model_validate(task)
        data.repository_ids = repository_ids_by_task.get(task.id, [])
        data.person_ids = person_ids_by_task.get(task.id, [])
        data.requester_ids = requester_ids_by_task.get(task.id, [])
        if task.waiting_on_person_id:
            person = waiting_people.get(task.waiting_on_person_id)
            data.waiting_on_name = person.name if person is not None else None
        reads.append(data)
    return reads


def _repository_names(session: Session, repository_ids: list[str]) -> list[str]:
    return [repo.name for repo in (session.get(Repository, rid) for rid in repository_ids) if repo is not None]


def _detail(session: Session, task: Task) -> TaskDetail:
    associations = session.exec(
        select(Association).where(Association.task_id == task.id).order_by(col(Association.created_at).desc())
    ).all()
    linked_person_ids = set(task_person_ids(session, task.id))
    details: list[AssociationDetail] = []
    suggested: list[Person] = []
    seen_suggested: set[str] = set()
    for assoc in associations:
        item = session.get(SourceItem, assoc.item_id)
        if item is None:
            continue
        details.append(
            AssociationDetail(
                id=assoc.id,
                note=assoc.note,
                created_at=assoc.created_at,
                item=ItemRead.model_validate(item),
            )
        )
        # People the item names (an issue/PR author, a commenter, a Slack
        # participant) that the task does not link yet become suggestions.
        for person_id in item_person_ids(session, item.id):
            if person_id in linked_person_ids or person_id in seen_suggested:
                continue
            person = session.get(Person, person_id)
            if person is not None:
                seen_suggested.add(person_id)
                suggested.append(person)
    worktrees = session.exec(
        select(Worktree)
        .where(Worktree.task_id == task.id)
        .order_by(
            case((col(Worktree.status) == WorktreeStatus.active, 0), else_=1),
            col(Worktree.created_at).desc(),
        )
    ).all()
    runs = session.exec(
        select(AgentRun).where(AgentRun.task_id == task.id).order_by(col(AgentRun.created_at).desc()).limit(20)
    ).all()
    sessions = session.exec(
        select(AgentSession).where(AgentSession.task_id == task.id).order_by(col(AgentSession.created_at).desc())
    ).all()
    changes = session.exec(
        select(Change).where(Change.task_id == task.id).order_by(col(Change.opened_at).desc()).limit(100)
    ).all()
    timeline = session.exec(
        select(TimelineEvent)
        .where(TimelineEvent.task_id == task.id)
        .order_by(col(TimelineEvent.created_at).desc())
        .limit(100)
    ).all()
    return TaskDetail(
        **_task_read(session, task).model_dump(),
        associations=details,
        people=[_person_read(session, person) for person in task_people(session, task.id)],
        requesters=[_person_read(session, person) for person in task_requesters(session, task.id)],
        suggested_people=[_person_read(session, person) for person in suggested],
        worktrees=[WorktreeRead.model_validate(w) for w in worktrees],
        runs=[run_read(session, r) for r in runs],
        sessions=[session_read(session, s) for s in sessions],
        changes=[ChangeRead.model_validate(c) for c in changes],
        timeline=[TimelineRead.model_validate(t) for t in timeline],
    )


def _link_item(session: Session, task_id: str, item: SourceItem, note: str = "") -> Association:
    """Create (or update) the association between a task and an item."""
    existing = session.exec(
        select(Association).where(Association.task_id == task_id, Association.item_id == item.id)
    ).first()
    assoc = existing or Association(task_id=task_id, item_id=item.id, note=note)
    if existing and note:
        assoc.note = note
    session.add(assoc)
    session.commit()
    session.refresh(assoc)
    # A linked source brings its people: everyone already on the item joins the task.
    link_item_people_to_task(session, task_id, item.id)
    # A linked GitHub issue or PR also brings its repository, when it is known.
    _link_repository_for_item(session, task_id, item)
    return assoc


def _populate_item_people(session: Session, item: SourceItem) -> None:
    """Fetch an item's people when it has a URL but none linked yet.

    An item created without a fetch (or whose fetch failed) carries no people,
    so linking it to a task would leave the task without the author and the
    commenters. Fetching here closes that gap for GitHub issues and PRs.
    """
    if not item.url or item_person_ids(session, item.id):
        return
    if item.source not in ("github", "slack"):
        return
    fetched = fetch_source(item.source, item.url, item.external_id, item.title)
    link_people_to_item(session, item.id, fetched.get("people") or [])
