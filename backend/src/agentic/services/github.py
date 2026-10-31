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


def refresh_github_cache(owner: str, repo: str, timeout: int = 300, types: str = "both") -> bool:
    """Refresh a repository's issues and PRs through ghx.

    ``ghx cache`` runs a delta fetch from the last cache write, so an unchanged
    repository costs a few small requests and a changed one picks up what
    changed. It is never a full re-fetch: the repository view's "refresh all"
    and the My PRs read both want current data, not a forced re-download.
    ``types`` narrows the fetch to ``"issues"`` or ``"prs"`` when the caller
    reads only one of them.

    That delta only holds for a repository whose cache a run has completed. On
    any other repository ghx walks the whole history, which takes minutes or
    hours, so a caller on a request path checks ``list_cached_repositories``
    first.
    """
    argv = ["ghx", "cache", "--repo", f"{owner}/{repo}"]
    if types != "both":
        argv += ["--type", types]
    return shell._run_cli(argv, timeout=timeout) is not None


#: The ``ghx repo list --json`` fields that tell a warmable cache apart.
_REPO_CACHE_FIELDS = "nameWithOwner,cachedAt"


def list_cached_repositories(timeout: int = 30) -> set[str] | None:
    """The repositories whose ghx cache a ``ghx cache`` run has completed.

    Only these refresh cheaply. A repository with no cache metadata (its items
    written by list and view reads alone) or a cache record with no completed
    run makes ``ghx cache`` walk the whole history, which a page load must
    never start. The result is lowercased ``owner/name`` so a caller can match
    it against a remote URL whose casing differs. None when ghx could not
    answer, which callers read as "nothing is warmable", the safe direction.
    """
    raw = shell._run_cli(["ghx", "repo", "list", "--json", _REPO_CACHE_FIELDS], timeout=timeout)
    if not raw:
        return None
    try:
        rows = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(rows, list):
        return None
    cached: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("nameWithOwner") or "").strip()
        cached_at = str(row.get("cachedAt") or "").strip()
        # A cache record with no completed run carries the zero instant.
        if not name or not cached_at or cached_at.startswith("0001-01-01"):
            continue
        cached.add(name.lower())
    return cached


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
        # GitHub's review decision for a pull request (APPROVED,
        # CHANGES_REQUESTED, REVIEW_REQUIRED, or null), so a reader can tell an
        # already-approved pull request from one still awaiting reviews. Null
        # for issues and for a repository whose branch requires no reviews.
        "review_decision": str(data.get("reviewDecision") or ""),
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
    """The reviewers assigned to a pull request, via ``ghx``.

    ghx carries the pull request's submitted reviews and the reviewers still
    requested, so this read needs no second tool. Each reviewer appears once:
    their latest decisive review state wins over a later plain comment, their
    last submitted review time is kept, and a reviewer a review is still
    requested from carries state ``PENDING`` with ``requested`` set. None when
    the read could not run.
    """
    raw = shell._run_cli(
        ["ghx", "pr", "view", str(number), "--repo", f"{owner}/{repo}", "--json"],
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
        if not isinstance(request, dict) or request.get("type") != "User":
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


_cached_github_login: str | None = None


def detect_github_login() -> str:
    """The login ``gh`` stores for github.com, or "" when unavailable.

    Only a fallback for when no ``github_login`` is configured. ``gh config get``
    reads gh's own config, so it costs no API call and works offline. gh stores
    no user when authentication comes from ``GH_TOKEN`` or ``GITHUB_TOKEN``
    alone, which reads as empty. The result is cached for the process, so a
    re-login to another account needs a restart or an explicit setting; both are
    cheap for a single-user local tool.
    """
    global _cached_github_login
    if _cached_github_login is not None:
        return _cached_github_login
    raw = shell._run_cli(["gh", "config", "get", "-h", "github.com", "user"], timeout=15)
    _cached_github_login = (raw or "").strip()
    return _cached_github_login


# --- Cycle-time data -------------------------------------------------------
#
# ghx's cache carries the reviews and review requests these series need, but it
# only answers for repositories it has cached, and the panel covers every
# repository with a GitHub remote. Filling a cache walks a repository's whole
# history, so these two reads go straight to the GitHub GraphQL API through
# ``gh``: one query per repository for closed issues and one for merged pull
# requests, with every review and review request the PR received.

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


def _graphql(
    query: str,
    variables: dict[str, Any],
    typed: frozenset[str] | set[str] = frozenset(),
) -> dict[str, Any] | None:
    """Run one GraphQL query through ``gh``. None when it could not run.

    ``gh`` sends ``-f`` values as strings and ``-F`` ones as literals, so a
    non-string variable (an Int, a Bool) must be named in ``typed``.
    """
    cmd = ["gh", "api", "graphql", "-f", f"query={query}"]
    for key, value in variables.items():
        if value is None:
            continue
        cmd.extend(["-F" if key in typed else "-f", f"{key}={value}"])
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
# ghx caches a repository's pull requests with the reviews, review requests,
# head-commit check rollup, and review-thread counts the My PRs page shows, so
# this read goes through ghx like every other GitHub read instead of querying
# GraphQL itself. ghx lists one repository at a time, so the rows come from the
# repositories the app knows: a pull request in a repository neither side knows
# is out of scope rather than silently missed.

#: The most open pull requests one repository's lookup reads.
MY_PULLS_LIMIT = 500

#: The fields a My PRs row reads. ghx's --json takes a field list, so the
#: payload stays to what the row needs instead of the whole record.
_MY_PULLS_FIELDS = (
    "number,title,url,isDraft,createdAt,updatedAt,reviewDecision,author,reviews,reviewRequests,checks,reviewThreads"
)

#: A check rollup state, as the CI badge reads it. ``EXPECTED`` means a check is
#: required but has not reported yet, which GitHub shows as pending too.
_CI_STATES = {
    "SUCCESS": "success",
    "FAILURE": "failure",
    "ERROR": "failure",
    "PENDING": "pending",
    "EXPECTED": "pending",
}


def _ci_state(checks: object) -> str:
    """A ghx check rollup as success / pending / failure / none."""
    rollup = checks if isinstance(checks, dict) else {}
    return _CI_STATES.get(str(rollup.get("state") or "").upper(), "none")


def _thread_counts(record: dict[str, Any]) -> tuple[int, int]:
    """The PR's (unresolved, total) review threads.

    ghx counts the first hundred threads, so a busier pull request undercounts
    the open ones; the total comes from the connection and stays exact.
    """
    threads = record.get("reviewThreads") or {}
    if not isinstance(threads, dict):
        return 0, 0
    return int(threads.get("open") or 0), int(threads.get("total") or 0)


def _reviews(record: dict[str, Any]) -> list[dict[str, Any]]:
    """The pull request's submitted reviews, as ghx reports them."""
    reviews = record.get("reviews") or []
    if not isinstance(reviews, list):
        return []
    return [review for review in reviews if isinstance(review, dict)]


def _approvers(reviews: list[dict[str, Any]]) -> list[str]:
    """The logins whose latest decisive review approves the pull request.

    Only decisive reviews are read, so a later plain comment neither drops an
    approval nor adds an approver, and a dismissed review drops it.
    """
    latest: dict[str, str] = {}
    order: list[str] = []
    for review in reviews:
        login = str((review.get("author") or {}).get("login") or "")
        state = str(review.get("state") or "").upper()
        if not login or state not in _DECISIVE_REVIEW_STATES:
            continue
        key = login.lower()
        if key not in latest:
            order.append(login)
        latest[key] = state
    return [login for login in order if latest[login.lower()] == "APPROVED"]


def _was_reviewed(reviews: list[dict[str, Any]], author: str) -> bool:
    """Whether anyone other than the pull request's author submitted a review.

    A review is any submission, a comment included. A pending review is not a
    submission yet, and the author's own comments do not mean the pull request
    received a review.
    """
    author = author.strip().lower()
    for review in reviews:
        if str(review.get("state") or "").upper() == "PENDING":
            continue
        login = str((review.get("author") or {}).get("login") or "").strip().lower()
        if login and login != author:
            return True
    return False


def _requested_reviewers(record: dict[str, Any]) -> list[str]:
    """The logins (or team names) GitHub still lists as requested reviewers."""
    requests = record.get("reviewRequests") or []
    if not isinstance(requests, list):
        return []
    names: list[str] = []
    for request in requests:
        if not isinstance(request, dict):
            continue
        name = request.get("login") or request.get("name")
        if name and name not in names:
            names.append(str(name))
    return names


def pr_review_request_message(url: str, title: str) -> str:
    """The Slack message a poke sends: a wave, a robot, and the PR's title as a link."""
    title = " ".join(str(title or "").split())
    # Slack's link label ends at "|", and the angle brackets delimit the link.
    for char in ("|", "<", ">"):
        title = title.replace(char, "-")
    label = f"<{url}|{title}>" if title else f"<{url}>"
    return f":wave::robot_face: I would love your review on this PR: {label}"


def _pull_row(record: dict[str, Any], repository: str, login: str = "") -> dict[str, Any] | None:
    """One ghx pull request record as the My PRs row, or None when it names no PR."""
    number = record.get("number")
    if not repository or number is None:
        return None
    decision = str(record.get("reviewDecision") or "")
    reviews = _reviews(record)
    open_threads, total_threads = _thread_counts(record)
    author = str((record.get("author") or {}).get("login") or login)
    return {
        "repository": repository,
        "number": int(number),
        "title": record.get("title") or "",
        "url": record.get("url") or "",
        "draft": bool(record.get("isDraft")),
        "created_at": record.get("createdAt"),
        "updated_at": record.get("updatedAt"),
        "review_decision": decision,
        # The decision is APPROVED only once the reviews the branch protection
        # requires are in, which is not the same as having one approval.
        "approved": decision == "APPROVED",
        "approvers": _approvers(reviews),
        "ci": _ci_state(record.get("checks")),
        "open_threads": open_threads,
        "threads_total": total_threads,
        # Whether anyone but the author has submitted a review, and who GitHub
        # still lists as requested reviewers; the inbox's review nudge reads both.
        "reviewed": _was_reviewed(reviews, author),
        "requested_reviewers": _requested_reviewers(record),
    }


def _updated_at(value: object) -> datetime:
    """A ghx timestamp as a comparable instant, for the cross-repository sort."""
    text = str(value or "").replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return datetime.min.replace(tzinfo=UTC)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def list_my_open_pulls(
    repositories: list[str] | tuple[str, ...],
    login: str,
    limit: int = MY_PULLS_LIMIT,
) -> list[dict[str, Any]] | None:
    """The open pull requests authored by *login* across *repositories*.

    *repositories* are ``owner/name`` strings. They are read together, so a
    slow repository does not add its latency to the others. None when ghx
    could not read any of them; a repository that could not be read on its own
    is left out of the rows and named in a warning instead of hiding the rest.
    """
    login = login.strip()
    if not login:
        return None
    wanted = list(dict.fromkeys(repo for repo in repositories if repo))
    if not wanted:
        return []
    listings = run_parallel([lambda repo=repo: _list_my_pulls_in(repo, login, limit) for repo in wanted])
    failed = [repo for repo, rows in zip(wanted, listings, strict=True) if rows is None]
    if len(failed) == len(wanted):
        return None
    if failed:
        log.warning("my pulls lookup failed for some repositories", repositories=failed)
    rows = [row for listing in listings if listing for row in listing]
    rows.sort(key=lambda row: _updated_at(row.get("updated_at")), reverse=True)
    return rows


def _list_my_pulls_in(repository: str, login: str, limit: int) -> list[dict[str, Any]] | None:
    """One repository's open pull requests by *login*, via ghx.

    ``ghx pr list`` serves from the repository's cache while it is fresh and
    fetches from GitHub when it is not, and ``--author`` keeps the read to the
    login's own pull requests. None when ghx could not run the read.
    """
    raw = shell._run_cli(
        [
            "ghx",
            "pr",
            "list",
            "--repo",
            repository,
            "--state",
            "open",
            "--author",
            login,
            "--limit",
            str(max(1, limit)),
            "--json",
            _MY_PULLS_FIELDS,
        ],
        timeout=120,
    )
    if not raw:
        return None
    try:
        records = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(records, list):
        return None
    return [row for record in records if isinstance(record, dict) and (row := _pull_row(record, repository, login))]


# --- A pull request's individual checks -------------------------------------
#
# The cached row carries only the head commit's rollup state and the number of
# checks. Which check failed is behind the page's CI badge, so that read
# happens when the badge's popover opens rather than on every page load.

#: A finished check with one of these conclusions passed. GitHub treats neutral
#: and skipped runs as non-blocking, so they read as success here too.
_CHECK_SUCCESS_STATES = frozenset({"SUCCESS", "NEUTRAL", "SKIPPED"})
#: A finished check with one of these conclusions failed.
_CHECK_FAILURE_STATES = frozenset({"FAILURE", "ERROR", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED", "STARTUP_FAILURE"})
#: The order the checks popover lists: what needs the author first.
_CHECK_STATE_ORDER = {"failure": 0, "pending": 1, "success": 2}
#: What a check that names no state of its own says.
_CHECK_STATE_LABELS = {"failure": "failed", "pending": "running", "success": "passed"}


def _check_state(check: dict[str, Any]) -> str:
    """One ghx check as failure / pending / success."""
    if str(check.get("type") or "") == "StatusContext":
        state = str(check.get("state") or "").upper()
    else:
        # A check run that has not finished carries no conclusion to read.
        if str(check.get("status") or "").upper() not in ("", "COMPLETED"):
            return "pending"
        state = str(check.get("conclusion") or "").upper()
    if state in _CHECK_SUCCESS_STATES:
        return "success"
    if state in _CHECK_FAILURE_STATES:
        return "failure"
    return "pending"


def _check_row(check: dict[str, Any]) -> dict[str, Any] | None:
    """One ghx check as the popover's row, or None when it is unnamed."""
    name = str(check.get("name") or "")
    if not name:
        return None
    state = _check_state(check)
    return {
        "name": name,
        "state": state,
        "url": str(check.get("url") or ""),
        "description": str(check.get("description") or "") or _CHECK_STATE_LABELS[state],
    }


def fetch_pull_checks(owner: str, repo: str, number: int) -> dict[str, Any] | None:
    """One pull request's head-commit checks, failing first.

    Returns ``{"rollup", "checks", "total"}``, or None when ghx could not read
    them. ghx lists the first hundred checks and keeps ``total`` exact, so the
    caller can say what it left out.
    """
    raw = shell._run_cli(
        ["ghx", "pr", "checks", str(number), "--repo", f"{owner}/{repo}", "--json"],
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
    entries = data.get("checks") or []
    if not isinstance(entries, list):
        return None
    checks = [row for entry in entries if isinstance(entry, dict) and (row := _check_row(entry)) is not None]
    checks.sort(key=lambda check: _CHECK_STATE_ORDER[check["state"]])
    return {
        "rollup": _CI_STATES.get(str(data.get("state") or "").upper(), "none"),
        "checks": checks,
        "total": int(data.get("total") or len(checks)),
    }


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
