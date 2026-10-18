"""Worktrees: isolated git checkouts attached to a task."""

from __future__ import annotations

import anyio
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case
from sqlmodel import Session, col, select

from ..crud import add_timeline, get_or_404, get_task_or_404
from ..db import get_session
from ..events import bus
from ..models.base import WorktreeStatus, utcnow
from ..models.repositories import Repository, TaskRepository, Worktree
from ..schemas.tasks import WorktreeRead
from ..schemas.worktrees import WorktreeCreate
from ..services.git import create_worktree, remove_worktree
from ..services.names import random_branch_name, worktree_path

router = APIRouter(prefix="/api/tasks", tags=["worktrees"])


@router.get("/{task_id}/worktrees", response_model=list[WorktreeRead])
def list_worktrees(task_id: str, session: Session = Depends(get_session)) -> list[Worktree]:
    get_task_or_404(session, task_id)
    return list(
        session.exec(
            select(Worktree)
            .where(Worktree.task_id == task_id)
            .order_by(
                case((col(Worktree.status) == WorktreeStatus.active, 0), else_=1),
                col(Worktree.created_at).desc(),
            )
        ).all()
    )


@router.post("/{task_id}/worktrees", response_model=WorktreeRead, status_code=201)
async def create_task_worktree(
    task_id: str, payload: WorktreeCreate, session: Session = Depends(get_session)
) -> Worktree:
    task = get_task_or_404(session, task_id)
    repository_id = payload.repository_id
    if not repository_id:
        member = session.exec(
            select(TaskRepository).where(TaskRepository.task_id == task.id).order_by(col(TaskRepository.created_at))
        ).first()
        repository_id = member.repository_id if member is not None else None
    if not repository_id:
        raise HTTPException(status_code=400, detail="No repository set; pass repository_id or set one on the task")
    repo = get_or_404(session, Repository, repository_id, "Repository not found")

    branch = payload.branch or random_branch_name(repo.path)
    path = worktree_path(task.id, branch)
    try:
        await anyio.to_thread.run_sync(create_worktree, repo.path, branch, path, payload.base or repo.default_branch)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    worktree = Worktree(task_id=task_id, repository_id=repo.id, branch=branch, path=path)
    session.add(worktree)
    session.commit()
    session.refresh(worktree)
    add_timeline(session, task_id, "worktree_created", f"Worktree {branch} at {path}", {"worktree_id": worktree.id})
    await bus.publish(f"task:{task_id}", {"kind": "task", "action": "worktrees_changed"})
    return worktree


@router.delete("/{task_id}/worktrees/{worktree_id}", status_code=204)
async def delete_worktree(task_id: str, worktree_id: str, session: Session = Depends(get_session)) -> None:
    worktree = session.get(Worktree, worktree_id)
    if worktree is None or worktree.task_id != task_id:
        raise HTTPException(status_code=404, detail="Worktree not found")
    repo = session.get(Repository, worktree.repository_id)
    if repo is not None:
        await anyio.to_thread.run_sync(remove_worktree, repo.path, worktree.path)
    worktree.status = WorktreeStatus.removed
    worktree.removed_at = utcnow()
    session.add(worktree)
    session.commit()
    add_timeline(
        session, task_id, "worktree_removed", f"Worktree {worktree.branch} removed", {"worktree_id": worktree.id}
    )
    await bus.publish(f"task:{task_id}", {"kind": "task", "action": "worktrees_changed"})
