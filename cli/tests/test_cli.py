import json

from agentic_cli import cli


def test_emit_json_is_parseable_and_ignores_text():
    cli.CONTEXT["format"] = "json"
    try:
        out = cli.emit({"a": 1}, "ignored")
        assert json.loads(out) == {"a": 1}
    finally:
        cli.CONTEXT["format"] = "auto"


def test_emit_text_preserves_brackets():
    cli.CONTEXT["format"] = "text"
    try:
        # Brackets must survive: moving through Rich as markup would drop them.
        assert cli.emit({"status": "open"}, "[open] p2") == "[open] p2"
    finally:
        cli.CONTEXT["format"] = "auto"


def test_client_has_no_server_command():
    # Serving belongs to the backend CLI (agentic-server).
    assert "problem" in cli.app
    assert "serve" not in cli.app
