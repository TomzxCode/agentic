"""Side-effectful helpers, grouped by purpose."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

from ..parallel import run_parallel
from . import shell
from .parsing import parse_github

log = structlog.get_logger(__name__)


GITHUB_REPO_RE = re.compile(r"github\.com[/:]([^/\s]+)/([^/\s#?]+?)(?:\.git)?(?:[/\s#?]|$)")


def github_owner_repo(value: str | None) -> tuple[str, str] | None:
    """Extract (owner, repo) from a GitHub URL or a git remote (https or ssh)."""
    match = GITHUB_REPO_RE.search(value or "")
    if not match:
        return None
    return match.group(1), match.group(2)


def list_github_issues(owner: str, repo: str, state: str = "open", limit: int = 20) -> list[dict[str, Any]] | None:
    """List issues for a repository via ghx. None on failure."""
    limit = max(1, min(limit, 1000))
    # ghx's --json is a boolean that emits the whole object list.
    raw = shell._run_cli(
        ["ghx", "issue", "list", "--repo", f"{owner}/{repo}", "--state", state, "--limit", str(limit), "--json"],
        timeout=60,
    )
    if not raw:
        return None
    issues: list[dict[str, Any]] = []
    for issue in json.loads(raw):
        issues.append(
            {
                "number": issue.get("number"),
                "title": issue.get("title") or "",
                "url": issue.get("url") or "",
                "state": issue.get("state") or "",
                "author": (issue.get("author") or {}).get("login"),
                "labels": [label.get("name") for label in issue.get("labels") or [] if isinstance(label, dict)],
                "body": issue.get("body") or "",
            }
        )
    return issues


def list_github_pulls(owner: str, repo: str, state: str = "open", limit: int = 100) -> list[dict[str, Any]] | None:
    """List a repository's pull requests via ghx. None on failure."""
    limit = max(1, min(limit, 1000))
    raw = shell._run_cli(
        [
            "ghx",
            "pr",
            "list",
            "--repo",
            f"{owner}/{repo}",
            "--state",
            state,
            "--limit",
            str(limit),
            "--json",
            "number,title,url,state,isDraft,mergedAt,createdAt,author,labels",
        ],
        timeout=90,
    )
    if not raw:
        return None
    pulls: list[dict[str, Any]] = []
    for pull in json.loads(raw):
        number = pull.get("number")
        if number is None:
            continue
        pulls.append(
            {
                "kind": "pr",
                "number": number,
                "title": pull.get("title") or "",
                "url": pull.get("url") or "",
                "state": pull.get("state") or "",
                # ghx reports an open draft only through this flag; the state
                # alone cannot tell it apart from a plain open pull request.
                "is_draft": bool(pull.get("isDraft")),
                # Set once a pull request is merged; null for issues and open PRs.
                "merged_at": pull.get("mergedAt"),
                # The object's own creation time, so a refresh policy can age it.
                "created_at": pull.get("createdAt"),
                "author": (pull.get("author") or {}).get("login"),
                "labels": [label.get("name") for label in pull.get("labels") or [] if isinstance(label, dict)],
            }
        )
    return pulls


def refresh_github_cache(owner: str, repo: str, timeout: int = 300) -> bool:
    """Force ghx to re-fetch a repository's issues and PRs from GitHub.

    ``ghx issue list``/``ghx pr list`` serve from the on-disk cache while it is
    fresh, so a listing on its own is not a refresh. The repository view's
    "refresh all" runs this first.
    """
    return shell._run_cli(["ghx", "cache", "--repo", f"{owner}/{repo}", "--force"], timeout=timeout) is not None


def list_github_repo_items(owner: str, repo: str, state: str = "all", limit: int = 1000) -> dict[str, Any] | None:
    """Every issue and pull request of a repository via ghx, tagged with its kind.

    Returns ``{"items": [...], "failed": [...]}`` where ``failed`` names each
    kind ghx could not list ("issues", "pull requests"), so a partial failure is
    visible rather than reading as an empty section. None only when both kinds
    fail. The two listings are independent, so they run together.
    """
    issues, pulls = run_parallel(
        [
            lambda: list_github_issues(owner, repo, state=state, limit=limit),
            lambda: list_github_pulls(owner, repo, state=state, limit=limit),
        ]
    )
    if issues is None and pulls is None:
        return None
    failed = []
    if issues is None:
        failed.append("issues")
    if pulls is None:
        failed.append("pull requests")
    # The listing only needs the metadata; an issue body would bloat the payload.
    listed_issues = [{**issue, "kind": "issue"} for issue in issues or [] if issue.get("number") is not None]
    for entry in listed_issues:
        entry.pop("body", None)
    return {"items": listed_issues + list(pulls or []), "failed": failed}


def fetch_github_issue(owner: str, repo: str, number: object, kind: str = "issue") -> dict[str, Any] | None:
    """Fetch a single issue or PR via ghx. None on failure."""
    sub = "pr" if kind == "pull_request" else "issue"
    raw = shell._run_cli(["ghx", sub, "view", str(number), "--repo", f"{owner}/{repo}", "--json"])
    if not raw:
        return None
    data = json.loads(raw)
    return {
        "number": data.get("number"),
        "title": data.get("title") or "",
        "url": data.get("url") or "",
        "state": data.get("state") or "",
        # ghx exposes the draft flag only on pull requests; the state alone
        # cannot distinguish an open draft from an open PR.
        "is_draft": bool(data.get("isDraft")),
        # Set only once a pull request is merged; null for issues and open PRs.
        "merged_at": data.get("mergedAt"),
        # The head commit, so a consumer can tell which commit a run targets.
        # Only pull requests have one.
        "head_sha": data.get("headRefOid") or "",
        # The object's own creation time, so a refresh policy can age it.
        "created_at": data.get("createdAt"),
        "author": (data.get("author") or {}).get("login"),
        "labels": [label.get("name") for label in data.get("labels") or [] if isinstance(label, dict)],
        "body": data.get("body") or "",
        "people": github_people(data),
    }


#: Review states that decide a reviewer's standing on the PR. A later plain
#: comment does not override an approval, a change request, or a dismissal.
_DECISIVE_REVIEW_STATES = frozenset({"APPROVED", "CHANGES_REQUESTED", "DISMISSED"})


def fetch_github_pull_reviewers(owner: str, repo: str, number: object) -> list[dict[str, Any]] | None:
    """The reviewers assigned to a pull request, via ``gh``.

    ``ghx`` reads issues and pull requests from its cache but does not carry
    reviews, so this one read goes through ``gh``. Each reviewer appears once:
    their latest decisive review state wins over a later plain comment, their
    last submitted review time is kept, and a reviewer a review is still
    requested from carries state ``PENDING`` with ``requested`` set. None when
    the read could not run.
    """
    raw = shell._run_cli(
        ["gh", "pr", "view", str(number), "--repo", f"{owner}/{repo}", "--json", "reviews,reviewRequests"],
        timeout=60,
    )
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    reviewers: dict[str, dict[str, Any]] = {}
    for review in data.get("reviews") or []:
        if not isinstance(review, dict):
            continue
        login = (review.get("author") or {}).get("login")
        if not login:
            continue
        state = str(review.get("state") or "").upper()
        submitted_at = review.get("submittedAt")
        current = reviewers.get(str(login).lower())
        if current is None:
            reviewers[str(login).lower()] = {
                "login": str(login),
                "state": state,
                "submitted_at": submitted_at,
                "requested": False,
            }
            continue
        if submitted_at and (not current["submitted_at"] or str(submitted_at) > str(current["submitted_at"])):
            current["submitted_at"] = submitted_at
        if state in _DECISIVE_REVIEW_STATES or current["state"] not in _DECISIVE_REVIEW_STATES:
            current["state"] = state
    for request in data.get("reviewRequests") or []:
        # A team request names a team, not a person, so only user requests are
        # listed: a reviewer row has someone a poke can reach.
        if not isinstance(request, dict) or request.get("__typename") != "User":
            continue
        login = request.get("login")
        if not login:
            continue
        current = reviewers.get(str(login).lower())
        if current is None:
            reviewers[str(login).lower()] = {
                "login": str(login),
                "state": "PENDING",
                "submitted_at": None,
                "requested": True,
            }
        else:
            current["state"] = "PENDING"
            current["requested"] = True
    return list(reviewers.values())


def create_github_issue(owner: str, repo: str, title: str, body: str = "") -> dict[str, Any] | None:
    """Create an issue in a repository with `gh`. None on failure.

    ghx has no issue-create command, so creating one is the single GitHub write
    that goes through `gh` instead. `gh issue create` prints the new issue's URL.
    """
    result = shell.run_cli_raw(
        ["gh", "issue", "create", "--repo", f"{owner}/{repo}", "--title", title, "--body", body],
    )
    if result is None:
        log.info("github issue create failed", error="gh is not installed")
        return None
    if result.returncode != 0:
        log.info("github issue create failed", error=result.stderr.strip())
        return None
    url = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
    parsed = parse_github(url)
    if not parsed:
        return None
    return {
        "number": int(parsed["number"]),
        "title": title,
        "url": url,
        "state": "OPEN",
        "body": body,
    }


def github_people(data: dict[str, Any]) -> list[dict[str, Any]]:
    """The people named by a ghx issue/PR payload: author, assignees, commenters.

    Each person carries a ``handle`` (the GitHub login), which is the identity
    used to de-duplicate them in the people directory.
    """
    people: list[dict[str, Any]] = []

    def add(login: object) -> None:
        if login:
            people.append({"name": str(login), "handle": str(login), "source": "github"})

    add((data.get("author") or {}).get("login"))
    for assignee in data.get("assignees") or []:
        if isinstance(assignee, dict):
            add(assignee.get("login"))
    for comment in data.get("comments") or []:
        if isinstance(comment, dict):
            add((comment.get("author") or {}).get("login"))
    return dedupe_people(people)


def dedupe_people(people: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the first entry per handle (or name), case-insensitively."""
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for person in people:
        key = str(person.get("handle") or person.get("name") or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(person)
    return result


def detect_github_login() -> str:
    """The login of the authenticated ``gh`` account, or "" when unavailable.

    Only a fallback for when no ``github_login`` is configured. The result is
    cached for the process, so a re-login to another account needs a restart or
    an explicit setting; both are cheap for a single-user local tool.
    """
    raw = shell._run_cli(["gh", "api", "user", "--jq", ".login"], timeout=15)
    return (raw or "").strip()


# --- Cycle-time data -------------------------------------------------------
#
# ghx's cache and list commands carry no reviews or timeline events, and gh's
# --json field set exposes neither, so these two reads go straight to the
# GitHub GraphQL API through ``gh`` (the same exception the reviewer read
# above makes). One query per repository for closed issues and one for merged
# pull requests, with every review and review request the PR received.

#: How long a repository's cycle-time data is reused before it is fetched again.
CYCLE_TIME_CACHE_SECONDS = 600

#: Merged PRs and closed issues the GraphQL search API will return, in total.
CYCLE_TIME_RESULT_LIMIT = 1000

_CYCLE_TIME_CACHE: dict[tuple[str, str, str], tuple[datetime, dict[str, list[dict[str, Any]]]]] = {}

_ISSUES_QUERY = """
query($owner: String!, $repo: String!, $since: DateTime!, $endCursor: String) {
  repository(owner: $owner, name: $repo) {
    issues(
      first: 100
      after: $endCursor
      filterBy: {since: $since, states: [CLOSED]}
      orderBy: {field: UPDATED_AT, direction: DESC}
    ) {
      pageInfo { hasNextPage endCursor }
      nodes { number createdAt closedAt }
    }
  }
}
"""

_PULLS_QUERY = """
query($owner: String!, $repo: String!, $endCursor: String) {
  repository(owner: $owner, name: $repo) {
    pullRequests(first: 100, after: $endCursor, states: [MERGED], orderBy: {field: UPDATED_AT, direction: DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number
        createdAt
        updatedAt
        mergedAt
        reviews(first: 100) {
          nodes { author { login } state submittedAt }
        }
        timelineItems(first: 100, itemTypes: [REVIEW_REQUESTED_EVENT]) {
          nodes {
            ... on ReviewRequestedEvent {
              createdAt
              requestedReviewer { ... on User { login } }
            }
          }
        }
      }
    }
  }
}
"""


def _graphql(query: str, variables: dict[str, Any]) -> dict[str, Any] | None:
    """Run one GraphQL query through ``gh``. None when it could not run."""
    cmd = ["gh", "api", "graphql", "-f", f"query={query}"]
    for key, value in variables.items():
        if value is None:
            continue
        cmd.extend(["-f", f"{key}={value}"])
    raw = shell._run_cli(cmd, timeout=120)
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or payload.get("errors"):
        if payload.get("errors"):
            log.warning("github graphql error", errors=payload.get("errors"))
        return None
    return payload


def _paginate_connection(
    query: str,
    variables: dict[str, Any],
    connection: Any,
    limit: int = CYCLE_TIME_RESULT_LIMIT,
    stop: Callable[[list[dict[str, Any]]], bool] | None = None,
) -> list[dict[str, Any]] | None:
    """Follow a connection's cursor until it is exhausted or ``limit`` rows are read.

    ``stop`` sees each page's nodes and returns True when nothing older can be
    wanted; the page it stopped on is still included.
    """
    rows: list[dict[str, Any]] = []
    cursor: str | None = None
    while len(rows) < limit:
        payload = _graphql(query, {**variables, "endCursor": cursor})
        if payload is None:
            return None
        try:
            node = connection(payload)
            page_info = node.get("pageInfo") or {}
            nodes = node.get("nodes") or []
            rows.extend(nodes)
        except (KeyError, TypeError, AttributeError):
            return None
        if not page_info.get("hasNextPage"):
            break
        if stop is not None and nodes and stop(nodes):
            break
        cursor = page_info.get("endCursor")
        if not cursor:
            break
    return rows[:limit]


# --- The viewer's own open pull requests ------------------------------------
#
# ghx lists a repository's pull requests but carries neither review threads nor
# a check rollup, and gh's --json field set exposes no resolved state for a
# thread, so this read goes to the GraphQL search API through ``gh`` (the same
# exception the cycle-time reads above make). One search finds every open pull
# request the login authored, with the thread, check, and review state the My
# PRs page shows.

#: The most open pull requests one lookup reads.
MY_PULLS_LIMIT = 500

_MY_PULLS_QUERY = """
query($q: String!, $endCursor: String) {
  search(query: $q, type: ISSUE, first: 50, after: $endCursor) {
    pageInfo { hasNextPage endCursor }
    nodes {
      ... on PullRequest {
        number
        title
        url
        isDraft
        createdAt
        updatedAt
        reviewDecision
        repository { nameWithOwner }
        commits(last: 1) { nodes { commit { statusCheckRollup { state } } } }
        reviewThreads(first: 100) {
          totalCount
          nodes { isResolved }
        }
        latestOpinionatedReviews(first: 50) { nodes { author { login } state } }
      }
    }
  }
}
"""

#: A check rollup state, as the CI badge reads it. ``EXPECTED`` means a check is
#: required but has not reported yet, which GitHub shows as pending too.
_CI_STATES = {
    "SUCCESS": "success",
    "FAILURE": "failure",
    "ERROR": "failure",
    "PENDING": "pending",
    "EXPECTED": "pending",
}


def _ci_state(node: dict[str, Any]) -> str:
    """The head commit's check rollup as success / pending / failure / none."""
    commits = (node.get("commits") or {}).get("nodes") or []
    commit = (commits[0] or {}).get("commit") if commits else None
    rollup = (commit or {}).get("statusCheckRollup") or {}
    return _CI_STATES.get(str(rollup.get("state") or "").upper(), "none")


def _thread_counts(node: dict[str, Any]) -> tuple[int, int]:
    """The PR's (unresolved, total) review threads.

    GitHub can filter threads by their resolution state but not a connection by
    it, so the unresolved count comes from the first page of threads; a pull
    request with more than a hundred threads reports the ones it read. The total
    comes from the connection itself, so it stays exact.
    """
    threads = node.get("reviewThreads") or {}
    nodes = threads.get("nodes") or []
    open_threads = sum(1 for thread in nodes if not thread.get("isResolved"))
    return open_threads, int(threads.get("totalCount") or len(nodes))


def _approvers(node: dict[str, Any]) -> list[str]:
    """The logins whose latest opinionated review approves the pull request.

    Only opinionated reviews are read, so a later plain comment neither drops an
    approval nor adds an approver, and a dismissed review drops it.
    """
    approvers: list[str] = []
    reviews = (node.get("latestOpinionatedReviews") or {}).get("nodes") or []
    for review in reviews:
        login = (review.get("author") or {}).get("login")
        if not login or str(review.get("state") or "").upper() != "APPROVED":
            continue
        if login not in approvers:
            approvers.append(login)
    return approvers


def _pull_row(node: dict[str, Any]) -> dict[str, Any] | None:
    """One GraphQL search node as the My PRs row, or None when it names no PR."""
    repository = str((node.get("repository") or {}).get("nameWithOwner") or "")
    number = node.get("number")
    if not repository or number is None:
        return None
    decision = str(node.get("reviewDecision") or "")
    open_threads, total_threads = _thread_counts(node)
    return {
        "repository": repository,
        "number": int(number),
        "title": node.get("title") or "",
        "url": node.get("url") or "",
        "draft": bool(node.get("isDraft")),
        "created_at": node.get("createdAt"),
        "updated_at": node.get("updatedAt"),
        "review_decision": decision,
        # The decision is APPROVED only once the reviews the branch protection
        # requires are in, which is not the same as having one approval.
        "approved": decision == "APPROVED",
        "approvers": _approvers(node),
        "ci": _ci_state(node),
        "open_threads": open_threads,
        "threads_total": total_threads,
    }


def search_my_open_pulls(login: str, limit: int = MY_PULLS_LIMIT) -> list[dict[str, Any]] | None:
    """The open pull requests authored by *login*, newest update first.

    None when GitHub could not be read or the search failed. Archived
    repositories are left out: their pull requests are not work in flight.
    """
    login = login.strip()
    if not login:
        return None
    query = f"is:pr is:open archived:false author:{login} sort:updated-desc"
    nodes = _paginate_connection(
        _MY_PULLS_QUERY,
        {"q": query},
        lambda payload: payload["data"]["search"],
        limit=max(1, limit),
    )
    if nodes is None:
        return None
    rows = [row for node in nodes if (row := _pull_row(node)) is not None]
    rows.sort(key=lambda row: str(row.get("updated_at") or ""), reverse=True)
    return rows


def fetch_github_cycle_time(
    owner: str,
    repo: str,
    since: datetime,
    *,
    refresh: bool = False,
) -> dict[str, list[dict[str, Any]]] | None:
    """A repository's closed issues and merged pull requests since ``since``.

    Returns ``{"issues": [...], "pulls": [...]}`` with ISO timestamps, or None
    when GitHub could not be read. Results are cached for
    ``CYCLE_TIME_CACHE_SECONDS`` per repository and window start.
    """
    key = (owner.lower(), repo.lower(), since.date().isoformat())
    cached = _CYCLE_TIME_CACHE.get(key)
    if cached is not None and not refresh:
        fetched_at, data = cached
        if datetime.now(UTC) - fetched_at < timedelta(seconds=CYCLE_TIME_CACHE_SECONDS):
            return data

    since_iso = since.astimezone(UTC).isoformat().replace("+00:00", "Z")
    raw_issues = _paginate_connection(
        _ISSUES_QUERY,
        {"owner": owner, "repo": repo, "since": since_iso},
        lambda payload: payload["data"]["repository"]["issues"],
    )
    if raw_issues is None:
        return None
    issues = [
        {
            "number": issue.get("number"),
            "created_at": issue.get("createdAt"),
            "closed_at": issue.get("closedAt"),
        }
        for issue in raw_issues
        if issue.get("closedAt")
    ]

    raw_pulls = _paginate_connection(
        _PULLS_QUERY,
        {"owner": owner, "repo": repo},
        lambda payload: payload["data"]["repository"]["pullRequests"],
        # Pull requests arrive newest-updated first, and a PR merged in the
        # window was updated in the window too, so a page entirely older than
        # the window ends the walk. A missing timestamp keeps the walk going.
        stop=lambda nodes: all(node.get("updatedAt") and node["updatedAt"] < since_iso for node in nodes),
    )
    if raw_pulls is None:
        return None
    pulls = []
    for pull in raw_pulls:
        if not pull.get("mergedAt"):
            continue
        reviews = [
            {
                "author": (review.get("author") or {}).get("login"),
                "state": review.get("state"),
                "submitted_at": review.get("submittedAt"),
            }
            for review in (pull.get("reviews") or {}).get("nodes") or []
            if review.get("submittedAt")
        ]
        requests = [
            {
                "reviewer": (event.get("requestedReviewer") or {}).get("login"),
                "requested_at": event.get("createdAt"),
            }
            for event in (pull.get("timelineItems") or {}).get("nodes") or []
            if event.get("createdAt")
        ]
        pulls.append(
            {
                "number": pull.get("number"),
                "created_at": pull.get("createdAt"),
                "merged_at": pull.get("mergedAt"),
                "reviews": reviews,
                "review_requests": requests,
            }
        )

    data = {"issues": issues, "pulls": pulls}
    _CYCLE_TIME_CACHE[key] = (datetime.now(UTC), data)
    return data


def _fetch_github(url: str, result: dict[str, Any]) -> None:
    parsed = parse_github(url)
    if not parsed:
        return
    issue = fetch_github_issue(parsed["owner"], parsed["repo"], parsed["number"], parsed["kind"])
    if issue is None:
        if not shell._cli_available("ghx"):
            result["error"] = "ghx is not installed; install it to fetch GitHub issues and pull requests"
        else:
            result["error"] = "ghx could not fetch the GitHub issue or pull request"
        return
    result["title"] = issue["title"] or result["title"]
    result["metadata"] = {
        **parsed,
        "state": issue["state"],
        "number": issue["number"],
        "is_draft": issue.get("is_draft", False),
        "merged_at": issue.get("merged_at"),
        "created_at": issue.get("created_at"),
        "author": issue.get("author"),
    }
    result["content"] = issue["body"]
    result["people"] = issue.get("people") or []
