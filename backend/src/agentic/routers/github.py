"""GitHub: list a repository's issues so a task can be imported from one."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from ..db import get_session
from ..models import Repository
from ..schemas import GithubIssue, GithubIssueCreate, GithubRepoListing
from ..services import (
    create_github_issue,
    fetch_github_issue,
    github_owner_repo,
    list_github_issues,
    list_github_repo_items,
    parse_github,
    refresh_github_cache,
)

router = APIRouter(prefix="/api/github", tags=["github"])


@router.get("/issue", response_model=GithubIssue)
def get_issue(url: str) -> GithubIssue:
    """Fetch a single issue or PR from its URL (ghx)."""
    parsed = parse_github(url)
    if not parsed:
        raise HTTPException(status_code=400, detail="Not a GitHub issue or pull request URL")
    issue = fetch_github_issue(parsed["owner"], parsed["repo"], parsed["number"], parsed["kind"])
    if issue is None:
        raise HTTPException(
            status_code=502,
            detail="Could not read the issue (is `ghx` installed and authenticated?)",
        )
    return GithubIssue.model_validate(issue)


def _resolve_owner_repo(
    session: Session,
    repository_id: str | None,
    owner: str | None,
    repo: str | None,
) -> tuple[str, str]:
    """Resolve a registered repository (or an explicit owner/repo) to (owner, repo)."""
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
    return owner, repo


@router.post("/issues", response_model=GithubIssue)
def create_issue(payload: GithubIssueCreate, session: Session = Depends(get_session)) -> GithubIssue:
    """Create an issue from a task's title/description (gh)."""
    if not payload.title.strip():
        raise HTTPException(status_code=400, detail="A title is required")
    owner, repo = _resolve_owner_repo(session, payload.repository_id, payload.owner, payload.repo)
    issue = create_github_issue(owner, repo, payload.title.strip(), payload.body or "")
    if issue is None:
        raise HTTPException(
            status_code=502,
            detail="Could not create the issue (is `gh` installed and authenticated?)",
        )
    return GithubIssue.model_validate(issue)


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
    owner, repo = _resolve_owner_repo(session, repository_id, owner, repo)

    issues = list_github_issues(owner, repo, state=state, limit=limit)
    if issues is None:
        raise HTTPException(
            status_code=502,
            detail="Could not read GitHub issues (is `ghx` installed and authenticated?)",
        )
    return [GithubIssue.model_validate(issue) for issue in issues]


@router.get("/repository", response_model=GithubRepoListing)
def list_repository(
    repository_id: str | None = None,
    owner: str | None = None,
    repo: str | None = None,
    state: str = "all",
    limit: int = 1000,
    refresh: bool = False,
    session: Session = Depends(get_session),
) -> GithubRepoListing:
    """List every issue and pull request of a repository (ghx), all states by default.

    Backs the repository view, which shows the whole repository rather than only
    the items already associated to tasks. With ``refresh``, ghx re-fetches the
    repository from GitHub first, so the call is a real refresh and not just a
    read of ghx's cache.
    """
    owner, repo = _resolve_owner_repo(session, repository_id, owner, repo)

    if refresh:
        refresh_github_cache(owner, repo)
    listing = list_github_repo_items(owner, repo, state=state, limit=limit)
    if listing is None:
        raise HTTPException(
            status_code=502,
            detail="Could not read GitHub issues (is `ghx` installed and authenticated?)",
        )
    return GithubRepoListing.model_validate(listing)
