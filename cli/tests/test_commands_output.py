"""Output format selection and the error-handling decorator."""

import json
from types import SimpleNamespace

from agentic_cli import cli, runtime
from agentic_cli.client import ApiError


def test_emit_auto_uses_json_off_a_tty(monkeypatch):
    runtime.CONTEXT["format"] = "auto"
    monkeypatch.setattr(cli.runtime, "sys", SimpleNamespace(stdout=SimpleNamespace(isatty=lambda: False), stderr=None))
    assert json.loads(runtime.emit({"a": 1}, "text")) == {"a": 1}

    monkeypatch.setattr(cli.runtime, "sys", SimpleNamespace(stdout=SimpleNamespace(isatty=lambda: True), stderr=None))
    assert runtime.emit({"a": 1}, "text") == "text"


def test_safe_handles_api_error_and_interrupt(capsys):
    @runtime.safe
    def api_failure():
        raise ApiError(404, "nope")

    assert api_failure() == 1
    err = capsys.readouterr().err
    assert "nope" in err and "HTTP 404" in err

    @runtime.safe
    def interrupted():
        raise KeyboardInterrupt

    assert interrupted() == 130
