"""Repositories: local git checkouts that problems create worktrees from."""

from __future__ import annotations

import contextlib
from pathlib import Path

import anyio
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete as sa_delete
from sqlalchemy import update as sa_update
from sqlmodel import Session, select

from ..db import get_session
from ..models import Problem, Repository, RepositoryGroupMember, Worktree
from ..schemas import (
    RepositoryBulkCreate,
    RepositoryBulkResult,
    RepositoryCreate,
    RepositoryRead,
)
from ..services import detect_default_branch, detect_remote_url, remove_worktree

router = APIRouter(prefix="/api/repositories", tags=["repositories"])


def _upsert_repository(
    session: Session,
    path_str: str,
    *,
    name: str | None = None,
    remote_url: str | None = None,
    default_branch: str | None = None,
) -> Repository:
    path = Path(path_str).expanduser().resolve()
    if not (path / ".git").exists():
        raise ValueError(f"{path} is not a git repository")
    repo = session.exec(select(Repository).where(Repository.path == str(path))).first()
    if repo is None:
        repo = Repository(name=name or path.name, path=str(path))
        session.add(repo)
    repo.name = name or repo.name or path.name
    repo.remote_url = remote_url or repo.remote_url or detect_remote_url(str(path))
    repo.default_branch = default_branch or repo.default_branch or detect_default_branch(str(path))
    session.add(repo)
    session.commit()
    session.refresh(repo)
    return repo


@router.get("", response_model=list[RepositoryRead])
def list_repositories(session: Session = Depends(get_session)) -> list[Repository]:
    return list(session.exec(select(Repository).order_by(Repository.created_at.desc())).all())


@router.post("", response_model=RepositoryRead, status_code=201)
def create_repository(payload: RepositoryCreate, session: Session = Depends(get_session)) -> Repository:
    try:
        return _upsert_repository(
            session,
            payload.path,
            name=payload.name,
            remote_url=payload.remote_url,
            default_branch=payload.default_branch,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/bulk", response_model=RepositoryBulkResult, status_code=201)
def create_repositories(payload: RepositoryBulkCreate, session: Session = Depends(get_session)) -> RepositoryBulkResult:
    added: list[RepositoryRead] = []
    errors: list[dict[str, str]] = []
    for path in payload.paths:
        try:
            added.append(RepositoryRead.model_validate(_upsert_repository(session, path)))
        except ValueError as exc:
            errors.append({"path": path, "error": str(exc)})
    return RepositoryBulkResult(added=added, errors=errors)


@router.get("/{repository_id}", response_model=RepositoryRead)
def get_repository(repository_id: str, session: Session = Depends(get_session)) -> Repository:
    repo = session.get(Repository, repository_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repository not found")
    return repo


@router.delete("/{repository_id}", status_code=204)
async def delete_repository(repository_id: str, session: Session = Depends(get_session)) -> None:
    repo = session.get(Repository, repository_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repository not found")
    for worktree in session.exec(select(Worktree).where(Worktree.repository_id == repo.id)).all():
        with contextlib.suppress(Exception):
            await anyio.to_thread.run_sync(remove_worktree, repo.path, worktree.path)
    session.execute(sa_delete(Worktree).where(Worktree.repository_id == repo.id))
    session.execute(sa_delete(RepositoryGroupMember).where(RepositoryGroupMember.repository_id == repo.id))
    session.execute(sa_update(Problem).where(Problem.repository_id == repo.id).values(repository_id=None))
    session.execute(sa_delete(Repository).where(Repository.id == repo.id))
    session.commit()
