"""GitHub: list a repository's issues so a task can be imported from one."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from ..crud import get_or_404
from ..db import get_session
from ..models.repositories import Repository
from ..schemas.github import GithubIssue, GithubIssueCreate, GithubPullPokeRequest, GithubRepoListing
from ..schemas.items import ItemGithubReviewer, ItemGithubReviewers, ItemPoke
from ..services.github import (
    create_github_issue,
    fetch_github_issue,
    fetch_github_pull_reviewers,
    github_owner_repo,
    list_github_issues,
    list_github_repo_items,
    refresh_github_cache,
)
from ..services.parsing import parse_github
from .items_refresh import sync_github_listing
from .review_pokes import poke_pull_request_reviewer as send_pull_review_poke

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


def _pull_request_fields(url: str) -> tuple[str, str, str]:
    """The (owner, repo, number) a pull request URL names, or a 400."""
    parsed = parse_github(url)
    if not parsed or parsed["kind"] != "pull_request":
        raise HTTPException(status_code=400, detail="Not a GitHub pull request URL")
    return parsed["owner"], parsed["repo"], parsed["number"]


@router.get("/pull/reviewers", response_model=ItemGithubReviewers)
def get_pull_request_reviewers(url: str) -> ItemGithubReviewers:
    """List a pull request's reviewers from its URL, read live through ``gh``.

    The standalone pull request view has no stored item to address, so this is
    the item endpoint's read keyed by the URL instead. A read that could not run
    reports its error rather than reading as "no reviewers".
    """
    owner, repo, number = _pull_request_fields(url)
    reviews = fetch_github_pull_reviewers(owner, repo, number)
    if reviews is None:
        return ItemGithubReviewers(
            error="Could not read this pull request's reviewers (is `gh` installed and authenticated?)"
        )
    return ItemGithubReviewers(reviewers=[ItemGithubReviewer.model_validate(review) for review in reviews])


@router.post("/pull/poke", response_model=ItemPoke)
def poke_reviewer_by_url(payload: GithubPullPokeRequest, session: Session = Depends(get_session)) -> ItemPoke:
    """Send a reviewer of a pull request a Slack message, addressed by URL."""
    _pull_request_fields(payload.url)
    return send_pull_review_poke(session, payload.url, payload.title, payload.login)


def _resolve_owner_repo(
    session: Session,
    repository_id: str | None,
    owner: str | None,
    repo: str | None,
) -> tuple[str, str]:
    """Resolve a registered repository (or an explicit owner/repo) to (owner, repo)."""
    if repository_id:
        repository = get_or_404(session, Repository, repository_id, "Repository not found")
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
    the items already associated to tasks. With ``refresh``, ghx runs a delta
    fetch against GitHub first, so the call picks up what changed instead of
    only reading ghx's cache; it does not force a full re-download. Either way
    the listing's state is written back onto the
    stored items it names, so the associated item is never read as older than the
    repository that shows it.
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
    sync_github_listing(session, owner, repo, listing["items"])
    return GithubRepoListing.model_validate(listing)
