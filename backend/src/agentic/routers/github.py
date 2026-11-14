"""GitHub: list a repository's issues so a task can be imported from one."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, col, select

from ..crud import get_or_404, get_task_or_404
from ..db import get_session
from ..models.items import Association, SourceItem
from ..models.repositories import Repository
from ..parallel import run_parallel
from ..review_auto_poke import next_poke_at
from ..schemas.github import (
    GithubIssue,
    GithubIssueCreate,
    GithubPullPokeRequest,
    GithubRepoListing,
    GithubTaskIssue,
    GithubTaskLinks,
)
from ..schemas.items import ItemGithubReviewer, ItemGithubReviewers, ItemPoke
from ..schemas.my_pulls import MyPullRead
from ..services.github import (
    apply_pull_facts,
    create_github_issue,
    fetch_github_issue,
    fetch_github_pull_reviewers_with_record,
    fetch_pull_row,
    github_owner_repo,
    list_github_issues,
    list_github_repo_items,
    pull_facts,
    pull_row_from_record,
)
from ..services.parsing import parse_github
from ..settings_store import resolve_github_login
from .items_refresh import sync_github_listing
from .review_pokes import poke_pull_request_reviewer as send_pull_review_poke

router = APIRouter(prefix="/api/github", tags=["github"])


@router.get("/task/{task_id}", response_model=GithubTaskLinks)
def get_task_links(task_id: str, session: Session = Depends(get_session)) -> GithubTaskLinks:
    """The GitHub issues and pull requests a task links, with their current state.

    The task view's Issue and PR tabs list what the task links, so this reads
    each link's state in one request instead of making a view fetch one per
    item. A link whose read fails still appears with the fields the stored item
    carries, so the list never drops something the task links.
    """
    get_task_or_404(session, task_id)
    associations = session.exec(
        select(Association).where(Association.task_id == task_id).order_by(col(Association.created_at))
    ).all()
    item_ids = [association.item_id for association in associations]
    items = session.exec(select(SourceItem).where(col(SourceItem.id).in_(item_ids))).all() if item_ids else []
    by_id = {item.id: item for item in items}
    parsed_links: list[tuple[dict, SourceItem]] = []
    seen: set[tuple[str, str, str, int]] = set()
    for item_id in item_ids:
        item = by_id.get(item_id)
        if item is None:
            continue
        parsed = parse_github(item.url or "")
        if not parsed:
            continue
        key = (
            parsed["kind"],
            parsed["owner"].lower(),
            parsed["repo"].lower(),
            int(parsed["number"]),
        )
        if key in seen:
            continue
        seen.add(key)
        parsed_links.append((parsed, item))

    login = resolve_github_login(session)
    issue_links = [(parsed, item) for parsed, item in parsed_links if parsed["kind"] == "issue"]
    pull_links = [(parsed, item) for parsed, item in parsed_links if parsed["kind"] == "pull_request"]

    issue_calls = [
        lambda parsed=parsed: fetch_github_issue(parsed["owner"], parsed["repo"], parsed["number"], "issue")
        for parsed, _ in issue_links
    ]
    pull_calls = [
        lambda parsed=parsed: fetch_pull_row(parsed["owner"], parsed["repo"], parsed["number"], login)
        for parsed, _ in pull_links
    ]
    results = run_parallel(issue_calls + pull_calls)

    issues: list[GithubTaskIssue] = []
    for (parsed, item), data in zip(issue_links, results[: len(issue_links)], strict=True):
        issues.append(
            GithubTaskIssue(
                number=int(parsed["number"]),
                title=(data or {}).get("title") or item.title or "",
                url=(data or {}).get("url") or item.url or "",
                state=str((data or {}).get("state") or (item.metadata_json or {}).get("state") or "").upper(),
            )
        )

    pulls: list[dict] = []
    for (parsed, item), row in zip(pull_links, results[len(issue_links) :], strict=True):
        if row is not None:
            pulls.append(row)
            continue
        meta = item.metadata_json or {}
        pulls.append(
            {
                "repository": f"{parsed['owner']}/{parsed['repo']}",
                "number": int(parsed["number"]),
                "title": item.title or "",
                "url": item.url or "",
                "state": str(meta.get("state") or "").upper(),
                "draft": bool(meta.get("is_draft")),
            }
        )

    # One mergeability read per repository, so a task linking several pull
    # requests of the same repository asks GitHub once.
    by_repository: dict[str, list[dict]] = {}
    for row in pulls:
        by_repository.setdefault(str(row.get("repository") or ""), []).append(row)
    for repository, rows in by_repository.items():
        apply_pull_facts(rows, pull_facts(repository, [row["number"] for row in rows]))

    return GithubTaskLinks(
        issues=issues,
        pulls=[MyPullRead.model_validate(row) for row in pulls],
    )


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
def get_pull_request_reviewers(url: str, session: Session = Depends(get_session)) -> ItemGithubReviewers:
    """List a pull request's reviewers from its URL, read live through ``gh``.

    The standalone pull request view has no stored item to address, so this is
    the item endpoint's read keyed by the URL instead. A read that could not run
    reports its error rather than reading as "no reviewers".
    """
    owner, repo, number = _pull_request_fields(url)
    result = fetch_github_pull_reviewers_with_record(owner, repo, number)
    if result is None:
        return ItemGithubReviewers(
            error="Could not read this pull request's reviewers (is `ghx` installed and authenticated?)"
        )
    pull = pull_row_from_record(result.record, f"{owner}/{repo}")
    return ItemGithubReviewers(
        reviewers=[ItemGithubReviewer.model_validate(review) for review in result.reviewers],
        next_poke_at=next_poke_at(session, pull),
    )


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
    session: Session = Depends(get_session),
) -> GithubRepoListing:
    """List every issue and pull request of a repository (ghx), all states by default.

    Backs the repository view, which shows the whole repository rather than only
    the items already associated to tasks. The listing reads ghx's cache and
    never refreshes it: the background job does that (``ghx_cache.py``), so this
    read never waits on a delta fetch. The listing's state is written back onto
    the stored items it names, so the associated item is never read as older
    than the repository that shows it.
    """
    owner, repo = _resolve_owner_repo(session, repository_id, owner, repo)

    listing = list_github_repo_items(owner, repo, state=state, limit=limit)
    if listing is None:
        raise HTTPException(
            status_code=502,
            detail="Could not read GitHub issues (is `ghx` installed and authenticated?)",
        )
    sync_github_listing(session, owner, repo, listing["items"])
    return GithubRepoListing.model_validate(listing)
