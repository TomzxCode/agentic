"""Repositories: local git checkouts that tasks create worktrees from."""

from __future__ import annotations

import contextlib
from pathlib import Path

import anyio
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete as sa_delete
from sqlalchemy import update as sa_update
from sqlmodel import Session, col, select

from ..db import get_session
from ..models.changes import Change
from ..models.repositories import Repository, RepositoryGroupMember, TaskRepository, Worktree
from ..schemas.repositories import RepositoryBulkCreate, RepositoryBulkResult, RepositoryCreate, RepositoryRead
from ..services.git import detect_default_branch, detect_remote_url, remove_worktree
from ..services.github import github_owner_repo

router = APIRouter(prefix="/api/repositories", tags=["repositories"])


def _default_name(remote_url: str | None, path: Path) -> str:
    """A repository's default name: ``owner/name`` when the remote says so."""
    parsed = github_owner_repo(remote_url)
    return f"{parsed[0]}/{parsed[1]}" if parsed else path.name


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
        repo = Repository(name=name or "", path=str(path))
        session.add(repo)
    repo.remote_url = remote_url or repo.remote_url or detect_remote_url(str(path))
    repo.default_branch = default_branch or repo.default_branch or detect_default_branch(str(path))
    repo.name = name or repo.name or _default_name(repo.remote_url, path)
    session.add(repo)
    session.commit()
    session.refresh(repo)
    return repo


@router.get("", response_model=list[RepositoryRead])
def list_repositories(session: Session = Depends(get_session)) -> list[Repository]:
    return list(session.exec(select(Repository).order_by(col(Repository.created_at).desc())).all())


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
    worktrees = session.exec(select(Worktree).where(Worktree.repository_id == repo.id)).all()
    for worktree in worktrees:
        with contextlib.suppress(Exception):
            await anyio.to_thread.run_sync(remove_worktree, repo.path, worktree.path)
    # Changes keep their provenance but not a dangling key: clear the repository
    # and any worktree of that repository before the rows are removed.
    worktree_ids = [worktree.id for worktree in worktrees]
    session.exec(sa_update(Change).where(col(Change.repository_id) == repo.id).values(repository_id=None))
    if worktree_ids:
        session.exec(sa_update(Change).where(col(Change.worktree_id).in_(worktree_ids)).values(worktree_id=None))
    session.exec(sa_delete(Worktree).where(col(Worktree.repository_id) == repo.id))
    session.exec(sa_delete(RepositoryGroupMember).where(col(RepositoryGroupMember.repository_id) == repo.id))
    session.exec(sa_delete(TaskRepository).where(col(TaskRepository.repository_id) == repo.id))
    session.exec(sa_delete(Repository).where(col(Repository.id) == repo.id))
    session.commit()
