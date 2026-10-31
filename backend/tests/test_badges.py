"""The sidebar nav badges: how much waits on each page, without a live read."""

from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlmodel import Session

from agentic import nav_badges
from agentic.config import settings
from agentic.db import engine
from agentic.main import app

FRONTMATTER = """---
feedback_id: {feedback_id}
kind: comment
repo: TomzxCode/agentic
pr: "42"
author: alice
created_at: "2026-10-01T00:00:00Z"
head_commit: abc1234
analyzed_at: "2026-10-02T00:00:00Z"
recommendation: implement
confidence: high
{extra}\
---

# Tighten the error message

## Comment

> please fix this
"""


def _row(repository="TomzxCode/agentic", number=42, **overrides):
    row = {
        "repository": repository,
        "number": number,
        "owner": repository.partition("/")[0],
        "name": repository.partition("/")[2],
        "state": "OPEN",
        "draft": False,
        "review_decision": "",
    }
    row.update(overrides)
    return row


def _request(repository="TomzxCode/agentic", number=42, **overrides):
    return SimpleNamespace(
        **{
            "repository": repository,
            "number": number,
            "title": "Awaiting a review",
            "url": "",
            "author": "bob",
            "state": "OPEN",
            "draft": False,
            "created_at": None,
            "source": "requested",
            **overrides,
        }
    )


def _write_feedback(root, feedback_id, extra=""):
    directory = root / "TomzxCode" / "agentic" / "pull-requests" / "42" / "feedback"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{feedback_id}.md").write_text(FRONTMATTER.format(feedback_id=feedback_id, extra=extra))


def test_awaiting_review_keeps_open_non_draft_unapproved_rows():
    assert nav_badges.awaiting_review(_row())
    assert nav_badges.awaiting_review(_row(review_decision="REVIEW_REQUIRED"))


def test_awaiting_review_drops_what_no_longer_waits():
    assert not nav_badges.awaiting_review(_row(draft=True))
    assert not nav_badges.awaiting_review(_row(review_decision="APPROVED"))
    assert not nav_badges.awaiting_review(_row(state="MERGED"))
    assert not nav_badges.awaiting_review(_row(state="closed"))


def test_review_count_merges_the_store_and_the_scan_without_double_counting(monkeypatch):
    store_rows = [_row(number=1), _row(number=2, review_decision="APPROVED")]
    scan_rows = [_request(number=1), _request(number=3), _request(number=4, draft=True)]

    monkeypatch.setattr(nav_badges, "collect_review_prs", lambda: store_rows)
    monkeypatch.setattr(nav_badges, "stored_review_requests", lambda session: scan_rows)

    # #1 is in both reads but counted once, #2 is approved, #4 is a draft.
    with Session(engine) as session:
        assert nav_badges.review_count(session) == 2


def test_feedback_count_counts_the_undecided_items(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "sdlc_dir", tmp_path)
    _write_feedback(tmp_path, "comment-1")
    _write_feedback(tmp_path, "comment-2", extra="decision: implement\ndecided_at: 2026-10-03T00:00:00Z\n")

    assert nav_badges.feedback_count() == 1


def test_my_pulls_count_counts_the_ones_needing_author_action(monkeypatch):
    pulls = [
        {"ci": "failure", "review_decision": "REVIEW_REQUIRED", "open_threads": 0, "approved": False, "draft": False},
        {"ci": "success", "review_decision": "APPROVED", "open_threads": 0, "approved": True, "draft": False},
        {"ci": "success", "review_decision": "REVIEW_REQUIRED", "open_threads": 2, "approved": False, "draft": False},
    ]
    seen: dict = {}

    def fake(login, repositories, refresh=False):
        seen["args"] = (login, repositories, refresh)
        return {"login": login, "pulls": pulls, "counts": {}, "error": None}

    monkeypatch.setattr(nav_badges, "fetch_my_pulls", fake)
    monkeypatch.setattr(nav_badges, "resolve_github_login", lambda session: "tomzx")
    monkeypatch.setattr(nav_badges, "known_github_repositories", lambda session: ["TomzxCode/agentic"])

    with Session(engine) as session:
        assert nav_badges.my_pulls_count(session) == 2
    # A badge is never a forced refresh: it reuses what the app already read.
    assert seen["args"] == ("tomzx", ["TomzxCode/agentic"], False)


def test_badges_endpoint_reports_the_three_counts(monkeypatch):
    monkeypatch.setattr("agentic.routers.badges.review_count", lambda session: 3)
    monkeypatch.setattr("agentic.routers.badges.my_pulls_count", lambda session: 2)
    monkeypatch.setattr("agentic.routers.badges.feedback_count", lambda: 1)

    with TestClient(app) as client:
        response = client.get("/api/badges")

    assert response.status_code == 200
    assert response.json() == {"reviews": 3, "my_pulls": 2, "feedback": 1}
