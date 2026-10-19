"""Read and record the must/should/may findings a PR's review skills recorded.

Each review skill that persists findings writes a ``<skill>.yaml`` state file
(``review.yaml`` for ``review-pr``, ``validate.yaml`` for ``validate-pr``,
``verify.yaml`` for ``verify-pr``) in the PR's review directory.  Every finding
carries a ``severity`` of ``must``, ``should``, or ``may``, plus a ``title``, a
``description``, a ``status``, and the ``first_seen_sha`` it was recorded at.

This module reads those state files so the app can offer the findings for the
reviewer to forward to the PR author, without this app posting anything itself.
It also writes the reviewer's decision on a finding (``include`` or ``skip``)
back onto that finding's entry, so the choice is recorded beside the finding.
"""

from __future__ import annotations

import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
import yaml

from .reviews import review_dir

log = structlog.get_logger(__name__)

#: The severities a finding can carry, most important first, which is also the
#: order the app shows them in.
SEVERITIES: tuple[str, ...] = ("must", "should", "may")

#: The decisions a reviewer can record on a finding: forward it to the PR author
#: (``include``) or leave it out (``skip``). The record sits on the finding's own
#: entry, beside the ``status`` the skill maintains.
DECISIONS: tuple[str, ...] = ("include", "skip")

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


def _timestamp(value: object) -> str:
    """A YAML timestamp as the ISO-8601 UTC string the state files write.

    An unquoted ``decided_at`` is parsed into a ``datetime`` by YAML, which would
    otherwise read as ``2026-10-19 02:34:23+00:00``; a naive one is taken as UTC.
    """
    if isinstance(value, datetime):
        moment = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return _text(value)


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


def _finding_spans(text: str) -> list[dict[str, Any]]:
    """Where each finding's entry sits in a state file, and where its keys are.

    A span carries the entry's title, its first and last line (``end`` is one
    past the last), the indent its keys sit at, and the line of each key, so a
    decision can be written onto one entry without touching the rest of the file
    (real state files are not always valid YAML, so they are edited line by line
    rather than re-serialized).
    """
    lines = text.splitlines()
    spans: list[dict[str, Any]] = []
    in_findings = False
    findings_indent = 0
    entry_indent: int | None = None
    key_indent: int | None = None
    current: dict[str, Any] | None = None

    def close(end: int) -> None:
        nonlocal current
        if current is not None:
            if key_indent is None:
                current["key_indent"] = current["indent"] + 2
            current["end"] = end
            spans.append(current)
            current = None

    for index, raw in enumerate(lines):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        if not in_findings:
            if stripped == "findings:":
                in_findings = True
                findings_indent = indent
            continue
        # A line back at the findings key's indent (or above it) ends the list.
        if indent <= findings_indent:
            break
        entry_match = _ENTRY_RE.match(raw)
        if entry_match and entry_indent in (None, indent):
            close(index)
            entry: dict[str, Any] = {"first": index, "indent": indent, "title": "", "keys": {}}
            current = entry
            entry_indent = indent
            key_indent = None
            # A key can sit on the dash itself: "- title: ...".
            key_match = _KEY_RE.match(entry_match.group("rest").strip())
            if key_match:
                key_indent = indent + 2
                entry["key_indent"] = key_indent
                entry["keys"][key_match.group("key")] = index
                entry["title"] = _unquote(key_match.group("value").strip())
            continue
        if current is None:
            continue
        key_match = _KEY_RE.match(raw)
        if not key_match:
            continue
        if key_indent is None:
            key_indent = indent
            current["key_indent"] = indent
        # Only keys at the entry's own key indent are metadata; a block scalar's
        # content sits deeper and an indented continuation is not a key.
        if indent != key_indent:
            continue
        key = key_match.group("key")
        current["keys"][key] = index
        if key == "title" and not current["title"]:
            current["title"] = _unquote(key_match.group("value").strip())

    close(len(lines))
    return spans


def _with_decision(text: str, title: str, decision: str, decided_at: str) -> str | None:
    """The file's text with the decision keys set on the entry titled *title*.

    Returns None when no entry carries that title. Only that entry's lines are
    replaced or extended; the rest of the file is left byte for byte, including
    the description scalars a strict YAML dump could not round-trip.
    """
    span = next((candidate for candidate in _finding_spans(text) if candidate["title"] == title), None)
    if span is None:
        return None
    lines = text.splitlines()
    pad = " " * span["key_indent"]
    updates = {"decision": f"decision: {decision}", "decided_at": f"decided_at: {decided_at}"}
    additions: list[str] = []
    for key, line in updates.items():
        index = span["keys"].get(key)
        if index is not None:
            lines[index] = pad + line
        else:
            additions.append(pad + line)
    if additions:
        # The entry's keys end where the next entry starts (or the list ends).
        lines[span["end"] : span["end"]] = additions
    new_text = "\n".join(lines)
    if text.endswith("\n"):
        new_text += "\n"
    return new_text


def _state_files(directory: Path) -> dict[str, list[Path]]:
    """The state files under a PR's review directory, keyed by skill.

    Hidden entries are skipped the way :func:`collect_findings` skips them, so a
    decision lands in a file the reader would also read.
    """
    files: dict[str, list[Path]] = {}
    for path in sorted(directory.rglob("*.yaml")):
        if any(part.startswith(".") for part in path.relative_to(directory).parts):
            continue
        files.setdefault(_state_step(path.stem), []).append(path)
    return files


def record_decisions(
    owner: str,
    repo: str,
    number: object,
    decisions: list[dict[str, Any]],
    *,
    decided_at: str | None = None,
) -> list[dict[str, Any]]:
    """Record the reviewer's include/skip decisions on a PR's findings.

    Each decision names a finding by the skill that recorded it (``step``) and
    its ``title`` (the finding's identity within that skill's state file), and
    carries a ``decision`` of ``include`` or ``skip``. All decisions are written
    in one pass: when any of them matches no finding nothing is written, so a
    batch either lands whole or not at all. Returns the decisions that matched
    nothing, which is empty on success.
    """
    directory = review_dir(owner, repo, number)
    if directory is None:
        return list(decisions)
    files = _state_files(directory)
    # One timestamp for the batch, and each file read and updated once, so a
    # select-all does not have later writes overwrite earlier ones.
    stamp = decided_at or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    pending: dict[Path, str] = {}
    missing: list[dict[str, Any]] = []
    for decision in decisions:
        step = _text(decision.get("step"))
        title = _text(decision.get("title"))
        value = _text(decision.get("decision")).lower()
        found = False
        for path in files.get(step, []):
            try:
                text = pending.get(path) or path.read_text(errors="replace")
            except OSError:
                continue
            updated = _with_decision(text, title, value, stamp)
            if updated is not None:
                pending[path] = updated
                found = True
                break
        if not found:
            missing.append(decision)
    if missing:
        return missing
    for path, text in pending.items():
        # Write beside the file and replace, so a crash cannot leave it truncated.
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp") as handle:
            handle.write(text)
            tmp = Path(handle.name)
        tmp.replace(path)
    return []


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
                    "decision": _text(entry.get("decision")).lower(),
                    "decided_at": _timestamp(entry.get("decided_at")),
                }
            )
    findings.sort(key=lambda finding: (_SEVERITY_ORDER[finding["severity"]], finding["step"], finding["title"].lower()))
    return findings
