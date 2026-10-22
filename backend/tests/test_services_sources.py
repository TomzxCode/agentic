"""The shell CLI helper and the source dispatcher."""

import subprocess

import structlog

from agentic.services import shell, sources


def test_run_cli_returns_none_for_a_missing_command(monkeypatch):
    monkeypatch.setattr(shell.shutil, "which", lambda name: None)
    assert shell._run_cli(["nope"]) is None


def test_run_cli_returns_stdout_only_on_success(monkeypatch):
    monkeypatch.setattr(shell.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(
        shell.subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, "out\n", "")
    )
    assert shell._run_cli(["x"]) == "out"

    monkeypatch.setattr(
        shell.subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(args, 1, "out", "err")
    )
    assert shell._run_cli(["x"]) is None


def test_run_cli_swallows_a_timeout(monkeypatch):
    monkeypatch.setattr(shell.shutil, "which", lambda name: "/usr/bin/" + name)

    def boom(*args, **kwargs):
        raise subprocess.TimeoutExpired("x", 1)

    monkeypatch.setattr(shell.subprocess, "run", boom)
    assert shell._run_cli(["x"]) is None


def test_run_cli_logs_ghx_and_slackx_calls_at_info(monkeypatch):
    monkeypatch.setattr(shell.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(
        shell.subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, "out", "")
    )

    with structlog.testing.capture_logs() as logs:
        shell._run_cli(["ghx", "issue", "list", "--repo", "o/r"])
        shell._run_cli(["slackx", "users", "list"])
        shell._run_cli(["gh", "api", "user"])  # not a tracked CLI
        shell.run_cli_raw(["ghx", "cache", "--force"])

    assert [entry["log_level"] for entry in logs] == ["info", "info", "info"]
    assert [entry["cmd"][0] for entry in logs] == ["ghx", "slackx", "ghx"]


def test_fetch_source_dispatches_and_swallows_errors(monkeypatch):
    calls: list = []
    monkeypatch.setattr(sources, "_fetch_github", lambda url, result: calls.append("github"))
    monkeypatch.setattr(sources, "_fetch_slack", lambda url, result: calls.append("slack"))
    monkeypatch.setattr(sources, "_fetch_url", lambda url, result: calls.append("url"))

    sources.fetch_source("github", "https://github.com/o/r/issues/1", None, "t")
    sources.fetch_source("slack", "https://x.slack.com/archives/C1/p1", None, "t")
    sources.fetch_source("url", "https://e.com", None, "t")
    sources.fetch_source("gdrive", "https://docs.google.com/document/d/abc/edit", None, "t")
    sources.fetch_source("note", None, None, "t")
    sources.fetch_source("slack", None, None, "t")  # no url means nothing to fetch
    assert calls == ["github", "slack", "url", "url"]

    def boom(url, result):
        raise RuntimeError("network down")

    monkeypatch.setattr(sources, "_fetch_url", boom)
    result = sources.fetch_source("url", "https://e.com", None, "t")
    assert result["content"] == "" and result["title"] == "t"


def test_fetch_source_stores_a_path_reference_without_its_content(tmp_path):
    target = tmp_path / "notes.md"
    target.write_text("# Title\nbody")

    file_result = sources.fetch_source("file", None, str(target), "")
    assert file_result["error"] is None
    assert file_result["title"] == "notes.md"
    assert file_result["metadata"]["kind"] == "file"
    # The fetch records stat data only; read_path provides the live content.
    assert file_result["content"] == ""

    folder = tmp_path / "project"
    (folder / "sub").mkdir(parents=True)
    (folder / "main.py").write_text("x")
    dir_result = sources.fetch_source("file", None, str(folder), "")
    assert dir_result["metadata"]["kind"] == "directory"
    assert dir_result["content"] == ""


def test_read_path_reads_a_file_and_a_directory(tmp_path):
    target = tmp_path / "notes.md"
    target.write_text("# Title\nbody")
    preview = sources.read_path(str(target))
    assert preview["kind"] == "file" and preview["content"] == "# Title\nbody"
    assert preview["truncated"] is False

    folder = tmp_path / "project"
    (folder / "sub").mkdir(parents=True)
    (folder / "main.py").write_text("x")
    listing = sources.read_path(str(folder))
    assert listing["kind"] == "directory"
    assert "main.py" in listing["content"] and "sub/" in listing["content"]


def test_read_path_does_not_cap_a_text_or_markdown_file(tmp_path):
    body = "# Title\n\n" + ("a long paragraph line\n" * 4000)
    target = tmp_path / "long.md"
    target.write_text(body)
    assert len(body) > 20_000

    preview = sources.read_path(str(target))
    assert preview["content"] == body
    assert preview["truncated"] is False


def test_fetch_source_reports_a_missing_path(tmp_path):
    result = sources.fetch_source("file", None, str(tmp_path / "gone"), "title")
    assert result["metadata"]["exists"] is False
    assert "does not exist" in result["error"]


def test_read_path_marks_a_binary_file(tmp_path):
    target = tmp_path / "blob.bin"
    target.write_bytes(b"\x00\x01\x02")
    result = sources.read_path(str(target))
    assert result["content"] == "Binary file (3 bytes)"


def test_fetch_url_extracts_title_and_strips_markup(monkeypatch):
    class Response:
        text = "<html><head><title>Page  Title</title></head><body><style>x</style>Hello <b>world</b></body></html>"

        def raise_for_status(self):
            return None

    monkeypatch.setattr(sources.httpx, "get", lambda *args, **kwargs: Response())
    result: dict = {"title": "", "content": "", "metadata": {}}
    sources._fetch_url("https://e.com", result)
    assert result["title"] == "Page Title"
    assert "Hello world" in result["content"]
    assert "<b>" not in result["content"]
