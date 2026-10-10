"""Problems: the unit of work everything else hangs off."""

from __future__ import annotations

import contextlib

import anyio
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete as sa_delete
from sqlmodel import Session, select

from ..crud import add_timeline, get_problem_or_404
from ..db import get_session
from ..events import bus
from ..models import (
    AgentEvent,
    AgentRun,
    Association,
    Problem,
    Repository,
    SourceItem,
    TimelineEvent,
    Worktree,
    utcnow,
)
from ..schemas import (
    AssociateRequest,
    AssociationDetail,
    ItemRead,
    ProblemCreate,
    ProblemDetail,
    ProblemRead,
    ProblemUpdate,
    RunRead,
    TimelineRead,
    WorktreeRead,
)
from ..services import remove_worktree
from .items import _upsert_item

router = APIRouter(prefix="/api/problems", tags=["problems"])


def _detail(session: Session, problem: Problem) -> ProblemDetail:
    associations = session.exec(
        select(Association).where(Association.problem_id == problem.id).order_by(Association.created_at.desc())
    ).all()
    details: list[AssociationDetail] = []
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
    worktrees = session.exec(
        select(Worktree).where(Worktree.problem_id == problem.id).order_by(Worktree.created_at.desc())
    ).all()
    runs = session.exec(
        select(AgentRun).where(AgentRun.problem_id == problem.id).order_by(AgentRun.created_at.desc()).limit(20)
    ).all()
    timeline = session.exec(
        select(TimelineEvent)
        .where(TimelineEvent.problem_id == problem.id)
        .order_by(TimelineEvent.created_at.desc())
        .limit(100)
    ).all()
    return ProblemDetail(
        **ProblemRead.model_validate(problem).model_dump(),
        associations=details,
        worktrees=[WorktreeRead.model_validate(w) for w in worktrees],
        runs=[RunRead.model_validate(r) for r in runs],
        timeline=[TimelineRead.model_validate(t) for t in timeline],
    )


@router.get("", response_model=list[ProblemRead])
def list_problems(
    status: str | None = None,
    q: str | None = None,
    session: Session = Depends(get_session),
) -> list[Problem]:
    query = select(Problem).order_by(Problem.updated_at.desc())
    if status:
        query = query.where(Problem.status == status)
    problems = list(session.exec(query).all())
    if q:
        needle = q.lower()
        problems = [
            p
            for p in problems
            if needle in p.title.lower()
            or needle in (p.description or "").lower()
            or needle in (p.summary or "").lower()
        ]
    return problems


@router.post("", response_model=ProblemRead, status_code=201)
async def create_problem(payload: ProblemCreate, session: Session = Depends(get_session)) -> Problem:
    problem = Problem(**payload.model_dump())
    session.add(problem)
    session.commit()
    session.refresh(problem)
    add_timeline(session, problem.id, "created", f"Problem created: {problem.title}")
    await bus.publish(f"problem:{problem.id}", {"kind": "problem", "action": "created"})
    return problem


@router.get("/{problem_id}", response_model=ProblemDetail)
def get_problem(problem_id: str, session: Session = Depends(get_session)) -> ProblemDetail:
    problem = get_problem_or_404(session, problem_id)
    return _detail(session, problem)


@router.patch("/{problem_id}", response_model=ProblemRead)
async def update_problem(problem_id: str, payload: ProblemUpdate, session: Session = Depends(get_session)) -> Problem:
    problem = get_problem_or_404(session, problem_id)
    data = payload.model_dump(exclude_unset=True)
    changed = set(data)
    for key, value in data.items():
        setattr(problem, key, value)
    problem.updated_at = utcnow()
    session.add(problem)
    session.commit()
    session.refresh(problem)
    if changed - {"summary", "next_steps"}:
        add_timeline(session, problem.id, "updated", f"Problem updated: {', '.join(sorted(changed))}")
    await bus.publish(f"problem:{problem.id}", {"kind": "problem", "action": "updated"})
    return problem


@router.delete("/{problem_id}", status_code=204)
async def delete_problem(problem_id: str, session: Session = Depends(get_session)) -> None:
    problem = get_problem_or_404(session, problem_id)

    # Remove worktrees from disk (best effort) before dropping their rows.
    repo_cache: dict[str, Repository] = {}
    for worktree in session.exec(select(Worktree).where(Worktree.problem_id == problem.id)).all():
        repo = repo_cache.get(worktree.repository_id) or session.get(Repository, worktree.repository_id)
        if repo is not None:
            repo_cache[repo.id] = repo
            with contextlib.suppress(Exception):
                await anyio.to_thread.run_sync(remove_worktree, repo.path, worktree.path)

    # Explicit, ordered deletes: SQLite enforces FKs (PRAGMA foreign_keys=ON),
    # so children must go before the problem row.
    run_ids = [r.id for r in session.exec(select(AgentRun).where(AgentRun.problem_id == problem.id)).all()]
    if run_ids:
        session.execute(sa_delete(AgentEvent).where(AgentEvent.run_id.in_(run_ids)))
    session.execute(sa_delete(AgentRun).where(AgentRun.problem_id == problem.id))
    session.execute(sa_delete(Association).where(Association.problem_id == problem.id))
    session.execute(sa_delete(Worktree).where(Worktree.problem_id == problem.id))
    session.execute(sa_delete(TimelineEvent).where(TimelineEvent.problem_id == problem.id))
    session.execute(sa_delete(Problem).where(Problem.id == problem.id))
    session.commit()
    await bus.publish("problems", {"kind": "problem", "action": "deleted", "id": problem_id})


@router.post("/{problem_id}/items", response_model=AssociationDetail, status_code=201)
async def associate_item(
    problem_id: str, payload: AssociateRequest, session: Session = Depends(get_session)
) -> AssociationDetail:
    get_problem_or_404(session, problem_id)
    if payload.item is not None:
        # Fetching (network/CLI) happens here; keep it off the event loop.
        item = await anyio.to_thread.run_sync(_upsert_item, session, payload.item)
    elif payload.item_id is not None:
        item = session.get(SourceItem, payload.item_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Item not found")
    else:
        raise HTTPException(status_code=400, detail="Provide item_id or item")

    existing = session.exec(
        select(Association).where(Association.problem_id == problem_id, Association.item_id == item.id)
    ).first()
    assoc = existing or Association(problem_id=problem_id, item_id=item.id, note=payload.note)
    if existing:
        assoc.note = payload.note or assoc.note
    session.add(assoc)
    session.commit()
    session.refresh(assoc)
    add_timeline(
        session,
        problem_id,
        "item_added",
        f"Associated [{item.source}] {item.title or item.url or item.id}",
        {"item_id": item.id},
    )
    await bus.publish(f"problem:{problem_id}", {"kind": "problem", "action": "items_changed"})
    return AssociationDetail(
        id=assoc.id, note=assoc.note, created_at=assoc.created_at, item=ItemRead.model_validate(item)
    )


@router.delete("/{problem_id}/items/{item_id}", status_code=204)
async def unassociate_item(problem_id: str, item_id: str, session: Session = Depends(get_session)) -> None:
    assoc = session.exec(
        select(Association).where(Association.problem_id == problem_id, Association.item_id == item_id)
    ).first()
    if assoc is None:
        raise HTTPException(status_code=404, detail="Association not found")
    session.delete(assoc)
    session.commit()
    add_timeline(session, problem_id, "item_removed", "Item unassociated", {"item_id": item_id})
    await bus.publish(f"problem:{problem_id}", {"kind": "problem", "action": "items_changed"})


@router.get("/{problem_id}/timeline", response_model=list[TimelineRead])
def get_timeline(problem_id: str, session: Session = Depends(get_session)) -> list[TimelineEvent]:
    get_problem_or_404(session, problem_id)
    return list(
        session.exec(
            select(TimelineEvent)
            .where(TimelineEvent.problem_id == problem_id)
            .order_by(TimelineEvent.created_at.desc())
        ).all()
    )


__all__ = ["router", "_detail"]
