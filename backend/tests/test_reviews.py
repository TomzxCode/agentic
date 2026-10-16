"""PR review reports: listing and reading the user-global ~/.sdlc store."""

import os

from fastapi.testclient import TestClient

from agentic.config import settings
from agentic.main import app
from agentic.reviews import list_report_files, read_report, report_identity, review_dir


def _write_reports(root, owner, repo, number):
    """Lay out a PR review directory the way the skills leave it behind."""
    directory = root / owner / repo / "pull-requests" / str(number)
    directory.mkdir(parents=True)
    (directory / "review-pr.abc1234.md").write_text("# Review\n\nLooks good.\n")
    # The stable "<skill>.report.md" name is a symlink to the per-run file.
    os.symlink("review-pr.abc1234.md", directory / "review-pr.report.md")
    (directory / "validate-pr.abc1234.md").write_text("# Validate\n\nConforms.\n")
    # Not a report: the findings state and the raw PR cache are left alone.
    (directory / "validate.yaml").write_text("verdict: approved\n")
    # A hidden directory (the store is a git checkout) is skipped.
    hidden = directory / ".git"
    hidden.mkdir()
    (hidden / "secret.md").write_text("hidden")
    feedback = directory / "feedback"
    feedback.mkdir()
    (feedback / "comment-1.md").write_text("# Feedback\n")
    # Deterministic ordering: review-pr newest, then validate, then feedback.
    os.utime(feedback / "comment-1.md", (500, 500))
    os.utime(directory / "validate-pr.abc1234.md", (1000, 1000))
    os.utime(directory / "review-pr.abc1234.md", (2000, 2000))
    return directory


def test_review_dir_resolves_with_a_different_casing(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "sdlc_dir", tmp_path)
    directory = _write_reports(tmp_path, "TomzxCode", "agentic", 42)
    # A GitHub URL may carry a different owner/repo casing than the store.
    assert review_dir("tomzxcode", "agentic", 42) == directory
    assert review_dir("tomzxcode", "agentic", "42") == directory
    assert review_dir("tomzxcode", "agentic", 99) is None
    assert review_dir("nobody", "agentic", 42) is None


def test_review_dir_falls_back_to_a_bare_repo_key(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "sdlc_dir", tmp_path)
    directory = _write_reports(tmp_path, "solo", "agentic", 7)
    # Rewrite the layout as {repo}/pull-requests/{n} (no owner level).
    bare = tmp_path / "agentic" / "pull-requests" / "7"
    bare.parent.mkdir(parents=True)
    directory.rename(bare)
    assert review_dir("solo", "agentic", 7) == bare


def test_list_report_files_returns_markdown_newest_first(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "sdlc_dir", tmp_path)
    _write_reports(tmp_path, "TomzxCode", "agentic", 42)

    reports = list_report_files("TomzxCode", "agentic", 42)
    names = [report["name"] for report in reports]
    assert names[0] == "review-pr.abc1234.md"  # newest modified first
    assert set(names) == {"review-pr.abc1234.md", "validate-pr.abc1234.md", "feedback/comment-1.md"}
    # The stable ".report.md" alias is a symlink; only its target is listed.
    assert "review-pr.report.md" not in names
    assert all(report["size"] > 0 for report in reports)
    assert list_report_files("TomzxCode", "agentic", 99) == []


def test_report_identity_splits_skill_and_commit():
    assert report_identity("analyze-test-coverage.e63d467.md") == ("analyze-test-coverage", "e63d467")
    assert report_identity("review-pr.344D6BF.md") == ("review-pr", "344d6bf")
    assert report_identity("feedback/comment-1.md") == (None, None)
    assert report_identity("validate-pr.no-issue.md") == (None, None)
    assert report_identity("gh-pr-view.md") == (None, None)


def test_list_report_files_tags_each_report_with_its_commit(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "sdlc_dir", tmp_path)
    _write_reports(tmp_path, "TomzxCode", "agentic", 42)

    by_name = {report["name"]: report for report in list_report_files("TomzxCode", "agentic", 42)}
    assert by_name["review-pr.abc1234.md"]["skill"] == "review-pr"
    assert by_name["review-pr.abc1234.md"]["commit"] == "abc1234"
    assert by_name["feedback/comment-1.md"]["commit"] is None


def test_read_report_reads_markdown_and_rejects_escapes(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "sdlc_dir", tmp_path)
    _write_reports(tmp_path, "TomzxCode", "agentic", 42)

    report = read_report("TomzxCode", "agentic", 42, "review-pr.abc1234.md")
    assert report is not None and "Looks good" in report["content"] and report["truncated"] is False

    # The stable ".report.md" alias resolves through its symlink.
    alias = read_report("TomzxCode", "agentic", 42, "review-pr.report.md")
    assert alias is not None and "Looks good" in alias["content"]

    nested = read_report("TomzxCode", "agentic", 42, "feedback/comment-1.md")
    assert nested is not None and "Feedback" in nested["content"]

    # A non-Markdown file, a missing file, and a path that escapes are all None.
    assert read_report("TomzxCode", "agentic", 42, "validate.yaml") is None
    assert read_report("TomzxCode", "agentic", 42, "missing.md") is None
    assert read_report("TomzxCode", "agentic", 42, "../../../../etc/passwd.md") is None
    assert read_report("nobody", "agentic", 42, "review-pr.abc1234.md") is None


def test_read_report_truncates_a_large_report(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "sdlc_dir", tmp_path)
    directory = _write_reports(tmp_path, "TomzxCode", "agentic", 42)
    (directory / "big.md").write_text("x" * 1_500_000)

    report = read_report("TomzxCode", "agentic", 42, "big.md")
    assert report is not None and report["truncated"] is True and len(report["content"]) == 1_000_000


def test_item_reviews_endpoints(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "sdlc_dir", tmp_path)
    _write_reports(tmp_path, "TomzxCode", "agentic", 42)

    with TestClient(app) as client:
        item = client.post(
            "/api/items",
            json={"url": "https://github.com/TomzxCode/agentic/pull/42", "fetch": False},
        ).json()

        listing = client.get(f"/api/items/{item['id']}/reviews").json()
        assert listing["path"].endswith("pull-requests/42")
        assert any(entry["name"] == "review-pr.abc1234.md" for entry in listing["files"])
        assert all(not entry["name"].endswith(".report.md") for entry in listing["files"])

        content = client.get(f"/api/items/{item['id']}/reviews/review-pr.report.md").json()
        assert "Looks good" in content["content"] and content["truncated"] is False

        nested = client.get(f"/api/items/{item['id']}/reviews/feedback/comment-1.md").json()
        assert "Feedback" in nested["content"]

        assert client.get(f"/api/items/{item['id']}/reviews/missing.md").status_code == 404
        assert client.get("/api/items/missing/reviews").status_code == 404

        # An issue is not a PR: it has no review reports.
        issue = client.post(
            "/api/items",
            json={"url": "https://github.com/TomzxCode/agentic/issues/7", "fetch": False},
        ).json()
        assert client.get(f"/api/items/{issue['id']}/reviews").json() == {"path": None, "files": []}

        client.delete(f"/api/items/{item['id']}")
        client.delete(f"/api/items/{issue['id']}")
