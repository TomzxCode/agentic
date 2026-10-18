"""The review queue: PRs in the local store with their review-step state."""

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from agentic import review_queue
from agentic.config import settings
from agentic.db import engine
from agentic.main import app
from agentic.models.items import Association
from agentic.review_queue import collect_review_prs, determine_stale_steps, readiness_signal


@pytest.fixture(autouse=True)
def _no_github(monkeypatch):
    """Never shell out to ghx: the queue falls back to the store's own values.

    A test that wants the GitHub fields patches ``review_queue.fetch_github_issue``
    itself.
    """
    review_queue._metadata_cache.clear()
    monkeypatch.setattr(review_queue, "fetch_github_issue", lambda *args, **kwargs: None)


def _marker(step, sha, verdict):
    return f'<!-- {{"step":"{step}","sha":"{sha}","verdict":"{verdict}"}} -->\n'


#: A complete, passing review at one commit, so no step is stale.
ALL_STEPS = {
    "review-pr": "pass",
    "validate-pr": "pass",
    "verify-pr": "pass",
    "analyze-test-coverage": "pass",
    "summarize-behavior-changes": "informational",
    "assess-pr-risk": "fast-track",
}


def _write_pr(root, owner, repo, number, sha="abc1234", steps=None, view=True):
    """Lay out a PR review directory the way the skills leave it behind."""
    directory = root / owner / repo / "pull-requests" / str(number)
    directory.mkdir(parents=True)
    for step, verdict in (steps or {}).items():
        (directory / f"{step}.{sha}.md").write_text(_marker(step, sha, verdict) + "# Report\n\nBody.\n")
    if view:
        (directory / "gh-pr-view.md").write_text(
            f"#{number} A pull request\n"
            "OPEN • opened by alice • 1 comment(s)\n\n"
            "Branch:    feature → main\n"
            "Created:   2026-01-12 06:14\n"
            f"URL:       https://github.com/{owner}/{repo}/pull/{number}\n\n"
            "── Comment 1 by bob (2026-01-12 07:00) ──\n\nHello\n"
        )
    return directory


def test_collect_review_prs_reads_markers_and_the_view_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "sdlc_dir", tmp_path)
    _write_pr(
        tmp_path,
        "TomzxCode",
        "agentic",
        42,
        sha="abc1234",
        steps=ALL_STEPS,
    )

    prs = collect_review_prs()
    assert len(prs) == 1
    pr = prs[0]
    assert (pr["owner"], pr["name"], pr["repository"], pr["number"]) == (
        "TomzxCode",
        "agentic",
        "TomzxCode/agentic",
        42,
    )
    assert pr["title"] == "A pull request"
    assert (pr["author"], pr["state"]) == ("alice", "OPEN")
    assert pr["url"] == "https://github.com/TomzxCode/agentic/pull/42"
    assert pr["head_commit"] == "abc1234"
    assert pr["stale_steps"] == []
    assert pr["readiness"] == "green"
    assert pr["status"] == "ready"
    assert pr["last_comment_by"] == "bob"
    assert pr["last_comment_at"] is not None
    assert pr["steps"]["review-pr"]["verdict"] == "pass"
    assert pr["steps"]["review-pr"]["report"] == "review-pr.abc1234.md"
    assert pr["steps"]["review-pr"]["stale"] is False


def test_a_step_that_does_not_cover_the_newest_commit_is_stale(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "sdlc_dir", tmp_path)
    directory = _write_pr(tmp_path, "TomzxCode", "agentic", 7, sha="aaaaaaa", steps={"validate-pr": "pass"})
    # A newer review at a second commit makes the validate report stale.
    (directory / "review-pr.bbbbbbb.md").write_text(_marker("review-pr", "bbbbbbb", "pass"))
    import os

    os.utime(directory / "validate-pr.aaaaaaa.md", (1000, 1000))
    os.utime(directory / "review-pr.bbbbbbb.md", (2000, 2000))

    pr = collect_review_prs()[0]
    assert pr["head_commit"] == "bbbbbbb"
    assert pr["steps"]["validate-pr"]["stale"] is True
    assert pr["steps"]["review-pr"]["stale"] is False
    # A stale validate cuts the chain: verify and review are stale too.
    assert "verify-pr" in pr["stale_steps"] and "review-pr" in pr["stale_steps"]
    assert pr["status"] == "needs-review"


def test_report_alias_without_a_commit_still_reports_its_verdict(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "sdlc_dir", tmp_path)
    directory = _write_pr(tmp_path, "TomzxCode", "agentic", 9, sha="abc1234", steps={}, view=False)
    (directory / "validate-pr.report.md").write_text(_marker("validate-pr", "abc1234", "pass"))

    pr = collect_review_prs()[0]
    assert pr["steps"]["validate-pr"]["verdict"] == "pass"
    assert pr["steps"]["validate-pr"]["commit"] == ""
    assert pr["head_commit"] == ""


def test_bare_repo_layout_is_read(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "sdlc_dir", tmp_path)
    _write_pr(tmp_path, "solo", "agentic", 3, sha="abc1234", steps={"review-pr": "pass"})
    # Rewrite the layout as {repo}/pull-requests/{n} (no owner level).
    bare = tmp_path / "agentic" / "pull-requests" / "3"
    bare.parent.mkdir(parents=True)
    (tmp_path / "solo" / "agentic" / "pull-requests" / "3").rename(bare)

    prs = collect_review_prs()
    assert len(prs) == 1 and prs[0]["repository"] == "agentic" and prs[0]["owner"] == ""


def test_determine_stale_steps_gates_the_chain():
    steps = {
        "assess-pr-risk": {"commit": "abc"},
        "summarize-behavior-changes": {"commit": "abc"},
        "analyze-test-coverage": {"commit": "abc"},
        "validate-pr": {"commit": "old"},
    }
    assert determine_stale_steps(steps, "abc") == ["validate-pr", "verify-pr", "review-pr"]
    steps["verify-pr"] = {"commit": "abc"}
    assert determine_stale_steps(steps, "abc") == ["validate-pr", "verify-pr", "review-pr"]


def test_readiness_signal_red_yellow_green():
    def steps(key, verdict):
        return {key: {"verdict": verdict}}

    assert readiness_signal(steps("review-pr", "pass"), [], False) == "green"
    assert readiness_signal(steps("review-pr", "fail"), [], False) == "red"
    assert readiness_signal(steps("assess-pr-risk", "hold"), [], False) == "red"
    # A stale step or a draft keeps a passing review yellow.
    assert readiness_signal(steps("review-pr", "pass"), ["review-pr"], False) == "yellow"
    assert readiness_signal(steps("review-pr", "pass"), [], True) == "yellow"


def test_review_queue_endpoint(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "sdlc_dir", tmp_path)
    _write_pr(tmp_path, "TomzxCode", "agentic", 42, sha="abc1234", steps=ALL_STEPS)

    with TestClient(app) as client:
        queue = client.get("/api/reviews").json()
        assert queue["counts"] == {"total": 1, "ready": 1, "blocked": 0}
        assert queue["root"] == str(tmp_path)
        pr = queue["prs"][0]
        assert pr["repository"] == "TomzxCode/agentic" and pr["number"] == 42
        assert pr["steps"]["review-pr"]["verdict"] == "pass"

        report = client.get(
            "/api/reviews/report/42/review-pr.abc1234.md",
            params={"repository": "TomzxCode/agentic"},
        ).json()
        assert "Body." in report["content"]

        assert (
            client.get("/api/reviews/report/42/missing.md", params={"repository": "TomzxCode/agentic"}).status_code
            == 404
        )


def test_review_queue_endpoint_merges_a_tracked_item(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "sdlc_dir", tmp_path)
    _write_pr(tmp_path, "TomzxCode", "agentic", 42, sha="abc1234", steps={"review-pr": "pass"}, view=False)

    with TestClient(app) as client:
        item = client.post(
            "/api/items",
            json={
                "url": "https://github.com/TomzxCode/agentic/pull/42",
                "fetch": False,
                "metadata_json": {"state": "MERGED", "is_draft": False, "author": "carol"},
            },
        ).json()
        pr = client.get("/api/reviews").json()["prs"][0]
        assert pr["item_id"] == item["id"]
        assert pr["state"] == "MERGED" and pr["author"] == "carol"
        client.delete(f"/api/items/{item['id']}")


def test_review_queue_reports_the_tasks_a_tracked_pr_is_associated_to(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "sdlc_dir", tmp_path)
    _write_pr(tmp_path, "TomzxCode", "agentic", 42, sha="abc1234", steps={"review-pr": "pass"}, view=False)

    with TestClient(app) as client:
        item = client.post(
            "/api/items",
            json={"url": "https://github.com/TomzxCode/agentic/pull/42", "fetch": False},
        ).json()
        task = client.post("/api/tasks", json={"title": "Land the PR"}).json()
        # Link the item to the task directly: the associate endpoint would fetch
        # the item from GitHub, which a unit test must not do.
        with Session(engine) as session:
            session.add(Association(task_id=task["id"], item_id=item["id"], note=""))
            session.commit()

        pr = client.get("/api/reviews").json()["prs"][0]
        assert pr["task_ids"] == [task["id"]]

        client.delete(f"/api/tasks/{task['id']}")
        client.delete(f"/api/items/{item['id']}")


def test_review_queue_pr_with_no_task_reports_no_task_ids(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "sdlc_dir", tmp_path)
    _write_pr(tmp_path, "TomzxCode", "agentic", 42, sha="abc1234", steps={"review-pr": "pass"}, view=False)

    with TestClient(app) as client:
        item = client.post(
            "/api/items",
            json={"url": "https://github.com/TomzxCode/agentic/pull/42", "fetch": False},
        ).json()
        pr = client.get("/api/reviews").json()["prs"][0]
        assert pr["item_id"] == item["id"]
        assert pr["task_ids"] == []
        client.delete(f"/api/items/{item['id']}")


def test_github_fields_come_from_ghx(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "sdlc_dir", tmp_path)
    _write_pr(tmp_path, "TomzxCode", "agentic", 42, sha="abc1234", steps=ALL_STEPS, view=False)
    monkeypatch.setattr(
        review_queue,
        "fetch_github_issue",
        lambda *args, **kwargs: {
            "title": "Fetched from ghx",
            "url": "https://github.com/TomzxCode/agentic/pull/42",
            "author": "dave",
            "state": "OPEN",
            "is_draft": False,
            "created_at": "2026-02-01T00:00:00Z",
        },
    )

    prs = collect_review_prs()
    review_queue.enrich_from_github(prs)
    pr = prs[0]
    assert pr["title"] == "Fetched from ghx"
    assert pr["author"] == "dave"
    assert pr["created_at"] == "2026-02-01T00:00:00Z"
    # A second pass reuses the cached lookup rather than shelling out again.
    calls: list = []
    monkeypatch.setattr(review_queue, "fetch_github_issue", lambda *args, **kwargs: calls.append(args))
    prs[0]["title"] = "stale"
    review_queue.enrich_from_github(prs)
    assert prs[0]["title"] == "Fetched from ghx"
    assert calls == []
