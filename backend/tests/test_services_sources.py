"""The shell CLI helper and the source dispatcher."""

import subprocess

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
