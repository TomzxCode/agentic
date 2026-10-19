"""PR-feedback queue: listing and deciding the user-global ~/.sdlc store."""

import pytest
from fastapi.testclient import TestClient

from agentic.config import settings
from agentic.feedback_store import (
    FEEDBACK_SECTIONS,
    discover_feedback,
    parse_feedback,
    write_decision,
)
from agentic.main import app

FRONTMATTER = """---
feedback_id: {feedback_id}
kind: comment
repo: TomzxCode/agentic
pr: "42"
author: alice
created_at: "{created_at}"
head_commit: abc1234
analyzed_at: "2026-10-02T00:00:00Z"
recommendation: {recommendation}
confidence: high
session_link: http://localhost:10000/?session=ses_test
{extra}\
---

# Tighten the error message

## Comment

> please fix this

[thread](https://github.com/TomzxCode/agentic/pull/42#discussion_r1)

## Analysis

This fails at `foo.py:12`.

## Recommended action

Do the thing.

## Suggested reply

Thanks, fixed in abc1234.
"""


@pytest.fixture(autouse=True)
def _no_ghx(monkeypatch):
    """Keep the PR-state enrichment off the network: leave states unknown."""

    def fake(rows, refresh=False):
        for row in rows:
            row["state"] = "OPEN"

    monkeypatch.setattr("agentic.routers.feedback.enrich_from_github", fake)


def _write(root, feedback_id, created_at="2026-10-01T00:00:00Z", recommendation="implement", extra=""):
    directory = root / "TomzxCode" / "agentic" / "pull-requests" / "42" / "feedback"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{feedback_id}.md"
    path.write_text(
        FRONTMATTER.format(
            feedback_id=feedback_id,
            created_at=created_at,
            recommendation=recommendation,
            extra=extra,
        )
    )
    return path


def _parsed(path):
    """Parse a file the test just wrote, asserting that it parsed."""
    item = parse_feedback(path)
    assert item is not None
    return item


def test_parse_feedback_reads_frontmatter_and_sections(tmp_path):
    path = _write(tmp_path, "comment-1")
    item = parse_feedback(path)
    assert item is not None
    assert item.feedback_id == "comment-1"
    assert item.repo == "TomzxCode/agentic"
    assert item.pr == "42"
    assert item.author == "alice"
    assert item.recommendation == "implement"
    assert item.confidence == "high"
    assert item.decision is None
    assert item.status == "pending"
    assert item.run_state == "none"
    assert item.title == "Tighten the error message"
    # Every named section in the file is captured, in the file's order (the
    # section order the view shows).
    assert list(item.sections) == [name for name in FEEDBACK_SECTIONS if name != "Suggested change"]
    assert "please fix this" in item.sections["Comment"]


def test_parse_feedback_skips_a_file_without_frontmatter(tmp_path):
    path = tmp_path / "plain.md"
    path.write_text("# No frontmatter here\n")
    assert parse_feedback(path) is None


def test_discover_puts_undecided_first_and_skips_dotfiles(tmp_path):
    _write(tmp_path, "comment-2", created_at="2026-10-03T00:00:00Z")
    _write(tmp_path, "comment-1", created_at="2026-10-01T00:00:00Z", extra="decision: implement\n")
    feedback_dir = tmp_path / "TomzxCode" / "agentic" / "pull-requests" / "42" / "feedback"
    (feedback_dir / ".comment-1.md.swp").write_text("junk")

    items = discover_feedback(tmp_path)
    # comment-1 carries a decision, so the undecided comment-2 leads.
    assert [item.feedback_id for item in items] == ["comment-2", "comment-1"]


def test_write_decision_records_and_clears_the_execution_marker(tmp_path):
    path = _write(tmp_path, "comment-1")

    write_decision(path, "implement")
    decided = _parsed(path)
    assert decided.decision == "implement"
    assert decided.decided_at
    assert decided.executed_at is None
    assert decided.run_state == "awaiting"

    # Running the decision stamps executed_at (the executor does this, not the
    # dashboard); re-recording the same decision leaves it alone so the item is
    # not re-queued.
    text = path.read_text().replace(
        f"decided_at: {decided.decided_at}",
        f"decided_at: {decided.decided_at}\nexecuted_at: 2026-10-04T00:00:00Z",
    )
    path.write_text(text)
    write_decision(path, "implement")
    assert _parsed(path).executed_at == "2026-10-04T00:00:00Z"

    # A different decision (and a reset) drops the stale marker.
    write_decision(path, "decline")
    changed = _parsed(path)
    assert changed.decision == "decline"
    assert changed.executed_at is None

    write_decision(path, None)
    reset = _parsed(path)
    assert reset.decision is None
    assert reset.status == "pending"
    assert reset.executed_at is None


def test_write_decision_rejects_a_file_without_frontmatter(tmp_path):
    path = tmp_path / "plain.md"
    path.write_text("# No frontmatter\n")
    with pytest.raises(ValueError):
        write_decision(path, "implement")


def test_list_feedback_endpoint(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "sdlc_dir", tmp_path)
    _write(tmp_path, "comment-1")
    _write(tmp_path, "comment-2", created_at="2026-10-03T00:00:00Z", recommendation="reject")

    with TestClient(app) as client:
        payload = client.get("/api/feedback").json()
        assert payload["root"] == str(tmp_path)
        assert payload["counts"]["pending"] == 2
        assert [item["feedback_id"] for item in payload["items"]] == ["comment-1", "comment-2"]
        first = payload["items"][0]
        assert first["status"] == "pending"
        assert first["run_state"] == "none"
        assert first["state"] == "open"
        assert first["pr_url"] == "https://github.com/TomzxCode/agentic/pull/42"
        assert first["sections"]["Comment"].startswith("> please fix")


def test_set_decision_endpoint(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "sdlc_dir", tmp_path)
    path = _write(tmp_path, "comment-1")

    with TestClient(app) as client:
        saved = client.post("/api/feedback/comment-1/decision", json={"decision": "defer"}).json()
        assert saved["decision"] == "defer"
        assert saved["status"] == "defer"
        assert saved["run_state"] == "awaiting"
        assert saved["decided_at"]
        assert "decision: defer" in path.read_text()

        reset = client.post("/api/feedback/comment-1/decision", json={"decision": None}).json()
        assert reset["decision"] is None
        assert reset["status"] == "pending"
        assert reset["run_state"] == "none"

        invalid = client.post("/api/feedback/comment-1/decision", json={"decision": "maybe"})
        assert invalid.status_code == 422

        missing = client.post("/api/feedback/comment-9/decision", json={"decision": "implement"})
        assert missing.status_code == 404


def test_list_feedback_reports_a_missing_root(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "sdlc_dir", tmp_path / "nope")
    with TestClient(app) as client:
        payload = client.get("/api/feedback").json()
        assert payload["root"] is None
        assert payload["items"] == []
