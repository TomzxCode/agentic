"""Side-effectful helpers, grouped by purpose."""

from __future__ import annotations

import json
import re
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
        # The object's own creation time, so a refresh policy can age it.
        "created_at": data.get("createdAt"),
        "author": (data.get("author") or {}).get("login"),
        "labels": [label.get("name") for label in data.get("labels") or [] if isinstance(label, dict)],
        "body": data.get("body") or "",
        "people": github_people(data),
    }


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
