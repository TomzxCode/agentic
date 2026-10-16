"""Read the user-global SDLC reviews store (PR review reports).

The review skills (``review-pr-full`` and its ``review-*`` chain) write their
Markdown reports under::

    $HOME/.sdlc/{owner}/{repository}/pull-requests/{number}/

That store lives outside any repository and is unrelated to a project's
``.sdlc/`` tree. This module resolves the directory for a GitHub pull request
and serves the Markdown reports it holds, so a PR item can show what the
reviews produced without leaving the app.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from .config import settings

REVIEWS_SUBDIR = "pull-requests"
#: A report larger than this is truncated rather than loaded whole, so a stray
#: huge file cannot blow up the response.
MAX_REPORT_BYTES = 1_000_000
#: The review skills name a per-run report ``<skill>.<short-sha>.md``; the sha
#: is the reviewed commit, which is what the reports of one run share.
REPORT_STEM_RE = re.compile(r"^(?P<skill>.+)\.(?P<commit>[0-9a-f]{7,40})\.md$", re.IGNORECASE)


def report_identity(name: str) -> tuple[str | None, str | None]:
    """Split a report file name into its (skill, commit), or (None, None).

    ``analyze-test-coverage.e63d467.md`` yields the skill and the short commit
    it reviews. A variant with no commit in its name (``validate-pr.no-issue.md``)
    or a raw cache (``gh-pr-view.md``) has neither.
    """
    match = REPORT_STEM_RE.match(Path(name).name)
    if not match:
        return None, None
    return match.group("skill"), match.group("commit").lower()


def _resolve_child(base: Path, name: str) -> Path | None:
    """Find ``base/name``, tolerating a case difference.

    The store is keyed by the repository's canonical owner/repo casing, while a
    GitHub URL's casing can differ, so an exact match is tried first and a
    case-insensitive sibling next.
    """
    if not base.is_dir():
        return None
    exact = base / name
    if exact.is_dir():
        return exact
    lowered = name.lower()
    for child in base.iterdir():
        if child.is_dir() and child.name.lower() == lowered:
            return child
    return None


def _review_dir_under(repo_dir: Path, number: object) -> Path | None:
    return _resolve_child(repo_dir / REVIEWS_SUBDIR, str(number))


def review_dir(owner: str, repo: str, number: object) -> Path | None:
    """The review-report directory for a PR, or None when it does not exist.

    The canonical layout is ``{owner}/{repo}/pull-requests/{number}``; a store
    keyed by the repository name alone is accepted as a fallback.
    """
    root = settings.sdlc_dir.expanduser()
    owner_dir = _resolve_child(root, owner)
    if owner_dir is not None:
        repo_dir = _resolve_child(owner_dir, repo)
        if repo_dir is not None:
            found = _review_dir_under(repo_dir, number)
            if found is not None:
                return found
    bare_repo_dir = _resolve_child(root, repo)
    if bare_repo_dir is not None:
        return _review_dir_under(bare_repo_dir, number)
    return None


def list_report_files(owner: str, repo: str, number: object) -> list[dict]:
    """The Markdown reports under a PR's review directory, newest first.

    Each entry carries the report's path relative to the PR directory (so a
    nested ``feedback/`` report stays addressable), its size, and when it was
    last modified. Hidden directories (``.git``) are skipped.
    """
    directory = review_dir(owner, repo, number)
    if directory is None:
        return []
    reports: list[dict] = []
    for path in directory.rglob("*.md"):
        # The stable ``<skill>.report.md`` names are symlinks to the per-run
        # ``<skill>.<sha>.md`` files; the targets are listed, so the aliases
        # would only duplicate them.
        if path.is_symlink() or not path.is_file():
            continue
        rel = path.relative_to(directory)
        if any(part.startswith(".") for part in rel.parts):
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        skill, commit = report_identity(rel.as_posix())
        reports.append(
            {
                "name": rel.as_posix(),
                "skill": skill,
                "commit": commit,
                "size": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=UTC),
            }
        )
    reports.sort(key=lambda report: (report["modified_at"], report["name"]), reverse=True)
    return reports


def read_report(owner: str, repo: str, number: object, name: str) -> dict | None:
    """Read one report by its path relative to the PR directory.

    Returns ``{"content": str, "truncated": bool}``, or None when the name is
    missing, escapes the directory, or is not a Markdown file. Traversal is
    rejected by resolving the target and requiring it to stay inside the
    directory.
    """
    directory = review_dir(owner, repo, number)
    if directory is None:
        return None
    root = directory.resolve()
    try:
        target = (root / name).resolve()
    except (OSError, ValueError):
        return None
    if target != root and root not in target.parents:
        return None
    if target.suffix.lower() != ".md" or not target.is_file():
        return None
    try:
        raw = target.read_bytes()
    except OSError:
        return None
    truncated = len(raw) > MAX_REPORT_BYTES
    return {"content": raw[:MAX_REPORT_BYTES].decode("utf-8", errors="replace"), "truncated": truncated}
