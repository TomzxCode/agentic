"""GitHub: list a repository's issues so a task can be imported from one."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from ..db import get_session
from ..models import Repository
from ..schemas import GithubIssue
from ..services import github_owner_repo, list_github_issues

router = APIRouter(prefix="/api/github", tags=["github"])


@router.get("/issues", response_model=list[GithubIssue])
def list_issues(
    repository_id: str | None = None,
    owner: str | None = None,
    repo: str | None = None,
    state: str = "open",
    limit: int = 20,
    session: Session = Depends(get_session),
) -> list[GithubIssue]:
    """List issues for a registered repository (or an explicit owner/repo)."""
    if repository_id:
        repository = session.get(Repository, repository_id)
        if repository is None:
            raise HTTPException(status_code=404, detail="Repository not found")
        parsed = github_owner_repo(repository.remote_url)
        if parsed is None:
            raise HTTPException(status_code=400, detail="Repository has no GitHub remote")
        owner, repo = parsed
    if not owner or not repo:
        raise HTTPException(status_code=400, detail="Provide repository_id, or owner and repo")

    issues = list_github_issues(owner, repo, state=state, limit=limit)
    if issues is None:
        raise HTTPException(
            status_code=502,
            detail="Could not read GitHub issues (is `ghx` installed and authenticated?)",
        )
    return [GithubIssue.model_validate(issue) for issue in issues]
