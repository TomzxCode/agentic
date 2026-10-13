"""Side-effectful helpers: git worktrees, source fetching, and context prompts."""

from __future__ import annotations

import json
import random
import re
import secrets
import shutil
import subprocess
from pathlib import Path
from typing import Any

import httpx
import structlog

from .config import settings

log = structlog.get_logger(__name__)


# --- git ------------------------------------------------------------------
def _git(args: list[str], cwd: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def detect_remote_url(repo_path: str) -> str | None:
    result = _git(["remote", "get-url", "origin"], cwd=repo_path, timeout=15)
    if result.returncode == 0:
        return result.stdout.strip() or None
    return None


def detect_default_branch(repo_path: str) -> str | None:
    result = _git(["symbolic-ref", "--short", "refs/remotes/origin/HEAD"], cwd=repo_path, timeout=15)
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip().removeprefix("origin/")
    for candidate in ("main", "master"):
        check = _git(["rev-parse", "--verify", candidate], cwd=repo_path, timeout=15)
        if check.returncode == 0:
            return candidate
    return None


def create_worktree(repo_path: str, branch: str, path: str, base: str | None = None) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    existing = _git(["rev-parse", "--verify", branch], cwd=repo_path, timeout=15)
    if existing.returncode == 0:
        result = _git(["worktree", "add", path, branch], cwd=repo_path)
    else:
        args = ["worktree", "add", "-b", branch, path]
        if base:
            args.append(base)
        result = _git(args, cwd=repo_path)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git worktree add failed")


def remove_worktree(repo_path: str, path: str) -> None:
    _git(["worktree", "remove", "--force", path], cwd=repo_path)
    _git(["worktree", "prune"], cwd=repo_path, timeout=15)


# --- source fetching ------------------------------------------------------
def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:48] or "item"


_ADJECTIVES = (
    "brisk",
    "calm",
    "clever",
    "curious",
    "dapper",
    "eager",
    "fuzzy",
    "gentle",
    "jolly",
    "lucky",
    "mellow",
    "nimble",
    "plucky",
    "quirky",
    "rusty",
    "silly",
    "snappy",
    "spry",
    "witty",
    "zesty",
)

_NOUNS = (
    "badger",
    "beetle",
    "bison",
    "crane",
    "dolphin",
    "falcon",
    "ferret",
    "gecko",
    "goose",
    "heron",
    "lemur",
    "llama",
    "marmot",
    "moose",
    "otter",
    "panda",
    "pelican",
    "puffin",
    "raven",
    "walrus",
)


def random_name() -> str:
    return f"{random.choice(_ADJECTIVES)}-{random.choice(_NOUNS)}"


def random_branch_name(repo_path: str, prefix: str = "agentic/") -> str:
    """A short memorable branch name that does not already exist in the repo."""
    for _ in range(10):
        candidate = f"{prefix}{random_name()}"
        if _git(["rev-parse", "--verify", candidate], cwd=repo_path, timeout=15).returncode != 0:
            return candidate
    return f"{prefix}{random_name()}-{secrets.token_hex(3)}"


def _run_cli(cmd: list[str], timeout: int = 60) -> str | None:
    if shutil.which(cmd[0]) is None:
        return None
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except (subprocess.TimeoutExpired, OSError) as exc:
        log.info("cli fetch failed", cmd=cmd[0], error=str(exc))
        return None
    return result.stdout.strip() if result.returncode == 0 else None


GITHUB_RE = re.compile(r"github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/(?P<kind>issues|pull)/(?P<num>\d+)")
SLACK_RE = re.compile(r"https://(?P<workspace>[^./]+)\.slack\.com/archives/(?P<channel>[^/]+)/p(?P<ts>\d+)")


def parse_github(url: str) -> dict[str, str] | None:
    match = GITHUB_RE.search(url or "")
    if not match:
        return None
    kind = "pull_request" if match.group("kind") == "pull" else "issue"
    return {
        "owner": match.group("owner"),
        "repo": match.group("repo"),
        "kind": kind,
        "number": match.group("num"),
        "external_id": f"{match.group('owner')}/{match.group('repo')}#{match.group('num')}",
    }


def parse_slack(url: str) -> dict[str, str] | None:
    match = SLACK_RE.search(url or "")
    if not match:
        return None
    ts = match.group("ts")
    return {
        "channel": match.group("channel"),
        "ts": f"{ts[:10]}.{ts[10:]}",
        "workspace": match.group("workspace"),
        "external_id": f"{match.group('channel')}:{ts}",
    }


GOOGLE_DOC_RE = re.compile(r"https?://(?:docs|drive)\.google\.com/[^/]+/d/([A-Za-z0-9_-]+)")
URL_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://\S+$")
BARE_HOST_RE = re.compile(r"^[a-z0-9](?:[a-z0-9\-]*[a-z0-9])?(?:\.[a-z0-9\-]+)+(?:[/?#]\S*)?$", re.IGNORECASE)


def looks_like_url(value: str | None) -> bool:
    """True when the value looks like a URL (scheme, or a bare domain)."""
    text = (value or "").strip()
    if not text or any(char.isspace() for char in text):
        return False
    return bool(URL_SCHEME_RE.match(text) or BARE_HOST_RE.match(text))


def infer_item_source(
    url: str | None = None,
    external_id: str | None = None,
    content: str | None = None,
) -> dict[str, str | None]:
    """Work out an item's source/kind/external id from what the user provided.

    Lets callers omit the source entirely: a GitHub or Slack link, a Google
    Docs/Drive link, another URL, or plain text each map to the right source.
    Plain text that is not a URL (or bare content) becomes a note.
    """
    text = (url or "").strip()
    if text and looks_like_url(text):
        github = parse_github(text)
        if github:
            return {"source": "github", "kind": github["kind"], "external_id": github["external_id"]}
        slack = parse_slack(text)
        if slack:
            return {"source": "slack", "kind": "thread", "external_id": slack["external_id"]}
        google = GOOGLE_DOC_RE.search(text)
        if google:
            return {"source": "gdrive", "kind": "doc", "external_id": google.group(1)}
        return {"source": "url", "kind": "", "external_id": external_id}
    return {"source": "note", "kind": "", "external_id": external_id}


def fetch_source(source: str, url: str | None, external_id: str | None, title: str) -> dict[str, Any]:
    """Best-effort metadata/content pull. Never raises."""

    result: dict[str, Any] = {"metadata": {}, "content": "", "title": title, "people": []}
    try:
        if source == "github" and url:
            _fetch_github(url, result)
        elif source == "slack" and url:
            _fetch_slack(url, result)
        elif url and (source in ("url", "gdrive") or source == "web"):
            _fetch_url(url, result)
    except Exception as exc:  # noqa: BLE001
        log.info("fetch_source failed", source=source, url=url, error=str(exc))
    return result


GITHUB_REPO_RE = re.compile(r"github\.com[/:]([^/\s]+)/([^/\s#?]+?)(?:\.git)?(?:[/\s#?]|$)")


def github_owner_repo(value: str | None) -> tuple[str, str] | None:
    """Extract (owner, repo) from a GitHub URL or a git remote (https or ssh)."""
    match = GITHUB_REPO_RE.search(value or "")
    if not match:
        return None
    return match.group(1), match.group(2)


def list_github_issues(owner: str, repo: str, state: str = "open", limit: int = 20) -> list[dict[str, Any]] | None:
    """List issues for a repository via ghx. None on failure."""
    limit = max(1, min(limit, 100))
    # ghx's --json is a boolean that emits the whole object list.
    raw = _run_cli(
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


def fetch_github_issue(owner: str, repo: str, number: object, kind: str = "issue") -> dict[str, Any] | None:
    """Fetch a single issue or PR via ghx. None on failure."""
    sub = "pr" if kind == "pull_request" else "issue"
    raw = _run_cli(["ghx", sub, "view", str(number), "--repo", f"{owner}/{repo}", "--json"])
    if not raw:
        return None
    data = json.loads(raw)
    return {
        "number": data.get("number"),
        "title": data.get("title") or "",
        "url": data.get("url") or "",
        "state": data.get("state") or "",
        "author": (data.get("author") or {}).get("login"),
        "labels": [label.get("name") for label in data.get("labels") or [] if isinstance(label, dict)],
        "body": data.get("body") or "",
        "people": github_people(data),
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


def _fetch_github(url: str, result: dict[str, Any]) -> None:
    parsed = parse_github(url)
    if not parsed:
        return
    issue = fetch_github_issue(parsed["owner"], parsed["repo"], parsed["number"], parsed["kind"])
    if issue is None:
        return
    result["title"] = issue["title"] or result["title"]
    result["metadata"] = {**parsed, "state": issue["state"], "number": issue["number"]}
    result["content"] = issue["body"]
    result["people"] = issue.get("people") or []


def slack_user_names() -> dict[str, str]:
    """Map Slack user ids to a display name, via the slackx cache. Best effort."""
    raw = _run_cli(["slackx", "users", "list", "--json", "--fields", "id,name,real_name"], timeout=30)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    users = data.get("users") if isinstance(data, dict) else data
    names: dict[str, str] = {}
    for user in users or []:
        if not isinstance(user, dict) or not user.get("id"):
            continue
        names[str(user["id"])] = user.get("real_name") or user.get("name") or str(user["id"])
    return names


def slack_people(payload: str, names: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """The distinct participants in a slackx thread payload.

    Each person carries a ``handle`` (the Slack user id) and a display name,
    resolved from ``names`` (or the message's ``user_name``) when available.
    """
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return []
    messages = data.get("messages") if isinstance(data, dict) else data
    names = names or {}
    people: list[dict[str, Any]] = []
    for message in messages or []:
        if not isinstance(message, dict):
            continue
        user_id = message.get("user")
        if not user_id:
            continue
        display = names.get(str(user_id))
        handle = str(user_id)
        if not display:
            # "tomzx (roctom)" -> name tomzx, handle roctom.
            raw_name = str(message.get("user_name") or "").strip()
            match = re.match(r"^(?P<name>.+?)\s*\((?P<handle>[^)]+)\)$", raw_name)
            if match:
                display = match.group("name").strip()
                handle = match.group("handle").strip()
            elif raw_name:
                display = raw_name
        people.append({"name": display or str(user_id), "handle": handle, "source": "slack"})
    return dedupe_people(people)


def _fetch_slack(url: str, result: dict[str, Any]) -> None:
    parsed = parse_slack(url)
    if parsed:
        result["metadata"] = parsed
    text = _run_cli(["slackx", "conversations", "show", url], timeout=90)
    if not text:
        text = _run_cli(["slackx", "conversations", "fetch", url], timeout=90)
    if text:
        result["content"] = text
    # A second, structured read of the same (now cached) thread names its people.
    raw = _run_cli(["slackx", "conversations", "show", url, "--json"], timeout=90)
    if raw:
        result["people"] = slack_people(raw, slack_user_names())


def _fetch_url(url: str, result: dict[str, Any]) -> None:
    response = httpx.get(url, follow_redirects=True, timeout=20, headers={"User-Agent": "agentic/0.1"})
    response.raise_for_status()
    html = response.text
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.DOTALL | re.IGNORECASE)
    if title_match and not result["title"]:
        result["title"] = re.sub(r"\s+", " ", title_match.group(1)).strip()
    body = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    body = re.sub(r"<[^>]+>", " ", body)
    body = re.sub(r"\s+", " ", body).strip()
    result["content"] = body[:20_000]


# --- agent context prompt -------------------------------------------------
CONTEXT_INSTRUCTIONS = """You are maintaining the living context for a tracked task.

Given the task and its associated items below, produce a concise, current
context so someone can resume in under a minute. Respond with ONLY a JSON
object (no prose, no code fences) of this exact form:

{
  "summary": "2-5 sentence current state of the task: what it is, what has happened, what matters now",
  "next_steps": [
    {"text": "a concrete, actionable next step", "done": false}
  ]
}

Rules:
- summary: at most 3 sentences (roughly 60 words). Prioritize what matters now.
- next_steps: 2-5 concrete actions, most important first. Drop completed ones.
- Be specific: name files, branches, issues, people where relevant.
- If a repository group is listed, treat those repositories as potentially
  relevant: consult them for context and say which one matters.
- Do not invent facts that are not supported by the items.
- Keep the JSON compact; do not exceed it.
"""


SLACK_PLACEHOLDER_TITLE = "Slack thread"


SUMMARIZE_INSTRUCTIONS = """You are naming and summarizing a task captured from a Slack thread.

Given the Slack conversation below, respond with ONLY a JSON object (no prose,
no code fences) of this exact form:

{
  "title": "a short, specific task title (at most ~80 characters)",
  "summary": "2-4 sentences on what the discussion is about and where it stands"
}

Rules:
- title: imperative and specific; name the people, systems, or files involved.
- summary: what is being discussed, what has been decided, and what matters now.
- Do not invent facts that are not in the conversation.
"""


def build_summary_prompt(thread: str) -> str:
    """The prompt that asks an agent to name and summarize an imported thread."""
    body = (thread or "").strip()[:20_000]
    return "\n".join([SUMMARIZE_INSTRUCTIONS, "", "# Slack conversation", "", body])


def build_context_prompt(task: dict[str, Any], items: list[dict[str, Any]]) -> str:
    lines = [CONTEXT_INSTRUCTIONS, "", f"# Task: {task['title']}", ""]
    if task.get("description"):
        lines += ["## Description", task["description"], ""]
    lines.append(f"## Status\n{task.get('status')}  (priority {task.get('priority')})")
    if task.get("repositories"):
        lines += ["", "## Repositories"]
        lines += [f"- {path}" for path in task["repositories"]]
    group = task.get("group")
    if group:
        lines += ["", f"## Repository group: {group['name']}"]
        if group.get("description"):
            lines.append(group["description"])
        repositories = group.get("repositories") or []
        if repositories:
            lines.append("These repositories may contain information relevant to this task:")
            lines += [f"- {path}" for path in repositories]
    if task.get("worktrees"):
        lines += ["", "## Active worktrees"]
        lines += [f"- {w['branch']} at {w['path']}" for w in task["worktrees"]]
    lines += ["", f"## Associated items ({len(items)})"]
    for item in items:
        lines.append(f"\n### [{item['source']}] {item.get('title') or item.get('url')}")
        if item.get("url"):
            lines.append(f"URL: {item['url']}")
        content = (item.get("content") or "").strip()
        if content:
            lines.append(content[:4000])
    return "\n".join(lines)


def _iter_json_objects(text: str):
    """Yield every balanced ``{...}`` candidate, respecting strings/escapes."""
    i = 0
    length = len(text)
    while i < length:
        if text[i] != "{":
            i += 1
            continue
        depth = 0
        in_string = False
        escaped = False
        for j in range(i, length):
            char = text[j]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
            elif char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    yield text[i : j + 1]
                    i = j + 1
                    break
        else:
            return


def _repair_truncated_json(candidate: str) -> str | None:
    """Close brackets/strings left open by a truncated JSON payload."""
    stack: list[str] = []
    in_string = False
    escaped = False
    for char in candidate:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "{[":
            stack.append(char)
        elif char in "}]" and stack:
            stack.pop()
    if not stack and not in_string:
        return None
    repaired = candidate
    if in_string:
        repaired += '"'
    for opener in reversed(stack):
        repaired += "}" if opener == "{" else "]"
    return repaired


def _try_parse(candidate: str, required: str = "summary") -> dict[str, Any] | None:
    if not isinstance(candidate, str):
        return None
    for attempt in (candidate, _repair_truncated_json(candidate)):
        if not attempt:
            continue
        try:
            data = json.loads(attempt)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and required in data:
            return data
    return None


def _json_candidates(text: str):
    """Yield slices of an agent reply that may hold a JSON object, best first."""
    for fenced in re.findall(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL):
        yield from _iter_json_objects(fenced)
    yield from _iter_json_objects(text)
    # Fallback for a payload truncated before its closing braces.
    first_brace = text.find("{")
    if first_brace != -1:
        yield text[first_brace:]


def _extract_json(text: str, required: str) -> dict[str, Any] | None:
    if not text:
        return None
    for candidate in _json_candidates(text):
        data = _try_parse(candidate, required)
        if data is not None:
            return data
    return None


def extract_context_json(text: str) -> dict[str, Any] | None:
    """Pull the first valid context JSON object out of an agent reply."""
    data = _extract_json(text, "summary")
    if data is None:
        return None
    steps = data.get("next_steps") or []
    data["next_steps"] = [
        {
            "text": str(s.get("text", s)) if isinstance(s, dict) else str(s),
            "done": bool(s.get("done")) if isinstance(s, dict) else False,
        }
        for s in steps
    ]
    return data


def extract_summary_json(text: str) -> dict[str, str] | None:
    """Pull the ``{title, summary}`` an agent produced for an imported thread.

    Either key is enough: a reply that only carries a summary still earns its
    summary, even though the title falls back to the placeholder.
    """
    data = _extract_json(text, "summary") or _extract_json(text, "title")
    if data is None:
        return None
    title = str(data.get("title") or "").strip()
    summary = str(data.get("summary") or "").strip()
    if not title and not summary:
        return None
    return {"title": title, "summary": summary}


def worktree_path(task_id: str, branch: str) -> str:
    return str(settings.worktree_root / task_id / slugify(branch))
