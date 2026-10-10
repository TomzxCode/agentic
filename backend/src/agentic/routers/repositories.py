"""Repositories: local git checkouts that problems create worktrees from."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..db import get_session
from ..models import Repository
from ..schemas import RepositoryCreate, RepositoryRead
from ..services import detect_default_branch, detect_remote_url

router = APIRouter(prefix="/api/repositories", tags=["repositories"])


@router.get("", response_model=list[RepositoryRead])
def list_repositories(session: Session = Depends(get_session)) -> list[Repository]:
    return list(session.exec(select(Repository).order_by(Repository.created_at.desc())).all())


@router.post("", response_model=RepositoryRead, status_code=201)
def create_repository(payload: RepositoryCreate, session: Session = Depends(get_session)) -> Repository:
    path = Path(payload.path).expanduser()
    if not (path / ".git").exists():
        raise HTTPException(status_code=400, detail=f"{path} is not a git repository")
    repo = Repository(
        name=payload.name or path.name,
        path=str(path),
        remote_url=payload.remote_url or detect_remote_url(str(path)),
        default_branch=payload.default_branch or detect_default_branch(str(path)),
    )
    session.add(repo)
    session.commit()
    session.refresh(repo)
    return repo


@router.get("/{repository_id}", response_model=RepositoryRead)
def get_repository(repository_id: str, session: Session = Depends(get_session)) -> Repository:
    repo = session.get(Repository, repository_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repository not found")
    return repo


@router.delete("/{repository_id}", status_code=204)
def delete_repository(repository_id: str, session: Session = Depends(get_session)) -> None:
    repo = session.get(Repository, repository_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repository not found")
    session.delete(repo)
    session.commit()
