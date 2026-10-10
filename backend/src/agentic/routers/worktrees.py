"""Worktrees: isolated git checkouts attached to a problem."""

from __future__ import annotations

import anyio
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..crud import add_timeline, get_problem_or_404
from ..db import get_session
from ..events import bus
from ..models import Repository, Worktree, WorktreeStatus, utcnow
from ..schemas import WorktreeCreate, WorktreeRead
from ..services import create_worktree, remove_worktree, slugify, worktree_path

router = APIRouter(prefix="/api/problems", tags=["worktrees"])


@router.get("/{problem_id}/worktrees", response_model=list[WorktreeRead])
def list_worktrees(problem_id: str, session: Session = Depends(get_session)) -> list[Worktree]:
    get_problem_or_404(session, problem_id)
    return list(
        session.exec(
            select(Worktree).where(Worktree.problem_id == problem_id).order_by(Worktree.created_at.desc())
        ).all()
    )


@router.post("/{problem_id}/worktrees", response_model=WorktreeRead, status_code=201)
async def create_problem_worktree(
    problem_id: str, payload: WorktreeCreate, session: Session = Depends(get_session)
) -> Worktree:
    problem = get_problem_or_404(session, problem_id)
    repository_id = payload.repository_id or problem.repository_id
    if not repository_id:
        raise HTTPException(status_code=400, detail="No repository set; pass repository_id or set one on the problem")
    repo = session.get(Repository, repository_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repository not found")

    branch = payload.branch or f"agentic/{slugify(problem.title)}-{problem.id[:4]}"
    path = worktree_path(problem.id, branch)
    try:
        await anyio.to_thread.run_sync(create_worktree, repo.path, branch, path, payload.base or repo.default_branch)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    worktree = Worktree(problem_id=problem_id, repository_id=repo.id, branch=branch, path=path)
    session.add(worktree)
    session.commit()
    session.refresh(worktree)
    add_timeline(session, problem_id, "worktree_created", f"Worktree {branch} at {path}", {"worktree_id": worktree.id})
    await bus.publish(f"problem:{problem_id}", {"kind": "problem", "action": "worktrees_changed"})
    return worktree


@router.delete("/{problem_id}/worktrees/{worktree_id}", status_code=204)
async def delete_worktree(problem_id: str, worktree_id: str, session: Session = Depends(get_session)) -> None:
    worktree = session.get(Worktree, worktree_id)
    if worktree is None or worktree.problem_id != problem_id:
        raise HTTPException(status_code=404, detail="Worktree not found")
    repo = session.get(Repository, worktree.repository_id)
    if repo is not None:
        await anyio.to_thread.run_sync(remove_worktree, repo.path, worktree.path)
    worktree.status = WorktreeStatus.removed
    worktree.removed_at = utcnow()
    session.add(worktree)
    session.commit()
    add_timeline(
        session, problem_id, "worktree_removed", f"Worktree {worktree.branch} removed", {"worktree_id": worktree.id}
    )
    await bus.publish(f"problem:{problem_id}", {"kind": "problem", "action": "worktrees_changed"})
