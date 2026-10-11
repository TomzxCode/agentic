"""Repository groups: named sets of repositories that inform a task's agent."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete as sa_delete
from sqlalchemy import update as sa_update
from sqlmodel import Session, col, select

from ..db import get_session
from ..models import Repository, RepositoryGroup, RepositoryGroupMember, Task
from ..schemas import RepositoryGroupCreate, RepositoryGroupRead, RepositoryGroupUpdate

router = APIRouter(prefix="/api/groups", tags=["groups"])


def _read(session: Session, group: RepositoryGroup) -> RepositoryGroupRead:
    member_ids = [
        member.repository_id
        for member in session.exec(
            select(RepositoryGroupMember).where(RepositoryGroupMember.group_id == group.id)
        ).all()
    ]
    return RepositoryGroupRead(
        id=group.id,
        name=group.name,
        description=group.description,
        repository_ids=member_ids,
        created_at=group.created_at,
    )


def _set_members(session: Session, group_id: str, repository_ids: list[str]) -> None:
    session.exec(sa_delete(RepositoryGroupMember).where(col(RepositoryGroupMember.group_id) == group_id))
    seen: set[str] = set()
    for repository_id in repository_ids:
        if repository_id in seen or session.get(Repository, repository_id) is None:
            continue
        seen.add(repository_id)
        session.add(RepositoryGroupMember(group_id=group_id, repository_id=repository_id))
    session.commit()


@router.get("", response_model=list[RepositoryGroupRead])
def list_groups(session: Session = Depends(get_session)) -> list[RepositoryGroupRead]:
    groups = session.exec(select(RepositoryGroup).order_by(col(RepositoryGroup.created_at).desc())).all()
    return [_read(session, group) for group in groups]


@router.get("/{group_id}", response_model=RepositoryGroupRead)
def get_group(group_id: str, session: Session = Depends(get_session)) -> RepositoryGroupRead:
    group = session.get(RepositoryGroup, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")
    return _read(session, group)


@router.post("", response_model=RepositoryGroupRead, status_code=201)
def create_group(payload: RepositoryGroupCreate, session: Session = Depends(get_session)) -> RepositoryGroupRead:
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Name is required")
    group = RepositoryGroup(name=payload.name.strip(), description=payload.description)
    session.add(group)
    session.commit()
    session.refresh(group)
    _set_members(session, group.id, payload.repository_ids)
    return _read(session, group)


@router.patch("/{group_id}", response_model=RepositoryGroupRead)
def update_group(
    group_id: str, payload: RepositoryGroupUpdate, session: Session = Depends(get_session)
) -> RepositoryGroupRead:
    group = session.get(RepositoryGroup, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        group.name = data["name"].strip() or group.name
    if "description" in data and data["description"] is not None:
        group.description = data["description"]
    session.add(group)
    session.commit()
    session.refresh(group)
    if data.get("repository_ids") is not None:
        _set_members(session, group.id, data["repository_ids"])
    return _read(session, group)


@router.delete("/{group_id}", status_code=204)
def delete_group(group_id: str, session: Session = Depends(get_session)) -> None:
    group = session.get(RepositoryGroup, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")
    session.exec(sa_delete(RepositoryGroupMember).where(col(RepositoryGroupMember.group_id) == group_id))
    session.exec(sa_update(Task).where(col(Task.group_id) == group_id).values(group_id=None))
    session.exec(sa_delete(RepositoryGroup).where(col(RepositoryGroup.id) == group_id))
    session.commit()
