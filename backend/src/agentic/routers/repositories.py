"""Repositories: local git checkouts that tasks create worktrees from."""

from __future__ import annotations

import contextlib
import subprocess
from functools import partial
from pathlib import Path

import anyio
import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete as sa_delete
from sqlalchemy import update as sa_update
from sqlmodel import Session, col, select

from ..crud import get_or_404
from ..db import get_session
from ..models.changes import Change
from ..models.repositories import Repository, RepositoryGroupMember, ReviewScanPolicy, TaskRepository, Worktree
from ..parallel import run_parallel
from ..schemas.repositories import (
    RepositoryBulkCreate,
    RepositoryBulkResult,
    RepositoryCreate,
    RepositoryRead,
    RepositoryUpdate,
)
from ..services.git import detect_default_branch, detect_remote_url, remove_worktree
from ..services.github import github_owner_repo

router = APIRouter(prefix="/api/repositories", tags=["repositories"])

log = structlog.get_logger(__name__)


def _default_name(remote_url: str | None, path: Path) -> str:
    """A repository's default name: ``owner/name`` when the remote says so."""
    parsed = github_owner_repo(remote_url)
    return f"{parsed[0]}/{parsed[1]}" if parsed else path.name


def _detect_origin(path_str: str) -> str | None:
    """A checkout's current ``origin`` URL, or None when it cannot be read.

    A checkout that was moved or deleted reads as None instead of raising, so a
    stale registration never fails the listing. A missing ``origin`` reads the
    same way, which is why the caller only adopts a value it actually got.
    """
    path = Path(path_str)
    if not (path / ".git").exists():
        return None
    try:
        return detect_remote_url(str(path))
    except (OSError, subprocess.TimeoutExpired):
        # An unreadable or wedged checkout must not take the whole listing down.
        return None


def _sync_remotes(session: Session, repositories: list[Repository]) -> list[Repository]:
    """Adopt each checkout's current ``origin``, and follow it in a derived name.

    ``origin`` can be added, removed, or retargeted after the repository was
    registered, which leaves the stored URL stale and the name derived from it
    with it. The stored URL is only replaced when the checkout reports one, so a
    missing remote never clears a value that is still useful; once a repository
    exists, ``origin`` is the source of truth, including over a ``remote_url``
    an API caller supplied at creation. The name follows only when it came from
    the URL (``owner/repo``) or the folder; a name set by hand stays.
    """
    detected = run_parallel([partial(_detect_origin, repository.path) for repository in repositories])
    changed = False
    for repository, remote_url in zip(repositories, detected, strict=True):
        path = Path(repository.path)
        # Adopt a changed origin. Its name follows only when it was derived
        # (owner/repo, the folder, or empty), so a hand-set name survives.
        if remote_url is not None and remote_url != repository.remote_url:
            derived = _default_name(repository.remote_url, path)
            log.info(
                "repository remote updated",
                repository=repository.id,
                path=repository.path,
                old=repository.remote_url,
                new=remote_url,
            )
            repository.remote_url = remote_url
            if repository.name in ("", derived, path.name):
                repository.name = _default_name(remote_url, path)
            session.add(repository)
            changed = True
            continue

        # The origin is unchanged or unreadable: still repair a name that was
        # never derived from a GitHub remote, such as the folder name left on a
        # checkout whose remote was added or recognized only later. The remote
        # we know about (detected, or the stored one when origin is gone) is
        # the source of truth for the name.
        effective_remote = remote_url if remote_url is not None else repository.remote_url
        if (
            effective_remote is not None
            and github_owner_repo(effective_remote) is not None
            and repository.name in ("", path.name)
            and _default_name(effective_remote, path) != repository.name
        ):
            log.info(
                "repository name repaired",
                repository=repository.id,
                path=repository.path,
                old=repository.name,
                new=_default_name(effective_remote, path),
            )
            repository.name = _default_name(effective_remote, path)
            session.add(repository)
            changed = True
    if changed:
        session.commit()
    return repositories


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
    repositories = list(session.exec(select(Repository).order_by(col(Repository.created_at).desc())).all())
    return _sync_remotes(session, repositories)


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
    repo = get_or_404(session, Repository, repository_id, "Repository not found")
    return repo


@router.patch("/{repository_id}", response_model=RepositoryRead)
def update_repository(
    repository_id: str,
    payload: RepositoryUpdate,
    session: Session = Depends(get_session),
) -> Repository:
    """Update the repository fields the app exposes (today, its review-scan policy)."""
    repo = get_or_404(session, Repository, repository_id, "Repository not found")
    fields = payload.model_dump(exclude_unset=True)
    review_scan = fields.get("review_scan")
    if review_scan is not None:
        allowed = {policy.value for policy in ReviewScanPolicy}
        if review_scan not in allowed:
            raise HTTPException(status_code=422, detail=f"review_scan must be one of {', '.join(sorted(allowed))}")
        repo.review_scan = review_scan
    session.add(repo)
    session.commit()
    session.refresh(repo)
    return repo


@router.delete("/{repository_id}", status_code=204)
async def delete_repository(repository_id: str, session: Session = Depends(get_session)) -> None:
    repo = get_or_404(session, Repository, repository_id, "Repository not found")
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
