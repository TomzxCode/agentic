"""Read the must/should/may findings a PR's review skills recorded.

Each review skill that persists findings writes a ``<skill>.yaml`` state file
(``review.yaml`` for ``review-pr``, ``validate.yaml`` for ``validate-pr``,
``verify.yaml`` for ``verify-pr``) in the PR's review directory.  Every finding
carries a ``severity`` of ``must``, ``should``, or ``may``, plus a ``title``, a
``description``, a ``status``, and the ``first_seen_sha`` it was recorded at.

This module reads those state files so the app can offer the findings for the
reviewer to forward to the PR author, without this app posting anything itself.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import structlog
import yaml

from .reviews import review_dir

log = structlog.get_logger(__name__)

#: The severities a finding can carry, most important first, which is also the
#: order the app shows them in.
SEVERITIES: tuple[str, ...] = ("must", "should", "may")

#: The findings-state file stem each skill writes: the state file drops the
#: skill's ``-pr`` suffix, so ``review-pr`` writes ``review.yaml``.
STATE_STEPS: dict[str, str] = {
    "review": "review-pr",
    "validate": "validate-pr",
    "verify": "verify-pr",
}
_SEVERITY_ORDER = {severity: index for index, severity in enumerate(SEVERITIES)}

_ENTRY_RE = re.compile(r"^(?P<indent>[ ]*)-\s*(?P<rest>.*)$")
_KEY_RE = re.compile(r"^(?P<indent>[ ]*)(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*:\s?(?P<value>.*)$")
_BLOCK_SCALAR_RE = re.compile(r"^[>|][+-]?$|^[+-][>|]$")


def _state_step(stem: str) -> str:
    return STATE_STEPS.get(stem, stem)


def _text(value: object) -> str:
    """A YAML scalar as a trimmed string; a missing key (None) reads as empty."""
    return "" if value is None else str(value).strip()


def _unquote(value: str) -> str:
    """Undo the surrounding quotes a YAML scalar may carry."""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        inner = value[1:-1]
        if value[0] == '"':
            return inner.replace('\\"', '"').replace("\\\\", "\\")
        return inner.replace("''", "'")
    return value


def _parse_findings_tolerantly(text: str) -> list[dict[str, Any]]:
    """Read the findings list from a state file that is not valid YAML.

    The skills write descriptions as unquoted scalars that can contain ``: ``,
    which YAML reads as a nested mapping, so a strict parse fails on real files.
    Read the list line by line instead: entries start with a ``-`` at one indent,
    their keys sit under it, and a value runs to the end of its line (or, for a
    ``>-``/``|`` block, over the following more-indented lines).
    """
    findings: list[dict[str, Any]] = []
    entry: dict[str, Any] | None = None
    entry_indent: int | None = None
    block_key: str | None = None
    block_indent = 0
    block_lines: list[str] = []
    in_findings = False
    findings_indent = 0

    def flush_block(current: dict[str, Any] | None) -> None:
        nonlocal block_key, block_lines
        if current is not None and block_key is not None:
            current[block_key] = " ".join(part.strip() for part in block_lines).strip()
        block_key, block_lines = None, []

    def flush_entry() -> None:
        nonlocal entry
        if entry:
            findings.append(entry)
        entry = None

    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        if not in_findings:
            if raw.strip() == "findings:":
                in_findings = True
                findings_indent = indent
            continue
        if block_key is not None:
            if indent > block_indent:
                block_lines.append(raw)
                continue
            flush_block(entry)
        entry_match = _ENTRY_RE.match(raw)
        if entry_match and indent > findings_indent and entry_indent in (None, indent):
            flush_entry()
            new_entry: dict[str, Any] = {}
            rest = entry_match.group("rest").strip()
            if rest:
                key_match = _KEY_RE.match(rest)
                if key_match and not _BLOCK_SCALAR_RE.match(key_match.group("value").strip()):
                    new_entry[key_match.group("key")] = _unquote(key_match.group("value").strip())
            entry = new_entry
            entry_indent = indent
            continue
        if entry is None or indent <= findings_indent:
            continue
        key_match = _KEY_RE.match(raw)
        if not key_match:
            continue
        key = key_match.group("key")
        value = key_match.group("value").strip()
        if _BLOCK_SCALAR_RE.match(value):
            block_key, block_indent = key, indent
            continue
        entry[key] = _unquote(value)

    flush_block(entry)
    flush_entry()
    return findings


def _read_findings(path: Path) -> list[dict[str, Any]]:
    """The ``findings`` entries in one state file, or [] when it has none.

    A state file that is valid YAML is parsed strictly; one that is not (an
    unquoted ``: `` in a description is the common case) is read tolerantly.
    """
    try:
        text = path.read_text(errors="replace")
    except OSError as exc:
        log.warning("could not read review findings state", path=str(path), error=str(exc))
        return []
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        log.warning("review findings state is not valid YAML; reading it tolerantly", path=str(path))
        return _parse_findings_tolerantly(text)
    if not isinstance(data, dict):
        return []
    return [entry for entry in (data.get("findings") or []) if isinstance(entry, dict)]


def collect_findings(owner: str, repo: str, number: object) -> list[dict[str, Any]]:
    """Every must/should/may finding recorded for a PR, in severity order.

    Reads the ``*.yaml`` state files under the PR's review directory and flattens
    their ``findings`` lists, keeping only entries whose severity is one of
    must/should/may (an entry without one is not a finding the reviewer would
    forward). A finding's ``step`` names the skill that recorded it. Returns an
    empty list when the PR has no review directory.
    """
    directory = review_dir(owner, repo, number)
    if directory is None:
        return []
    findings: list[dict[str, Any]] = []
    for path in sorted(directory.rglob("*.yaml")):
        if any(part.startswith(".") for part in path.relative_to(directory).parts):
            continue
        step = _state_step(path.stem)
        for entry in _read_findings(path):
            severity = _text(entry.get("severity")).lower()
            if severity not in _SEVERITY_ORDER:
                continue
            findings.append(
                {
                    "step": step,
                    "title": _text(entry.get("title")),
                    "description": _text(entry.get("description")),
                    "severity": severity,
                    "status": _text(entry.get("status")),
                    "sha": _text(entry.get("first_seen_sha")),
                }
            )
    findings.sort(key=lambda finding: (_SEVERITY_ORDER[finding["severity"]], finding["step"], finding["title"].lower()))
    return findings
