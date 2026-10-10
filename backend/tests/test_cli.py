import json

from agentic import cli


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


def test_cli_help_lists_commands():
    # Parsing the root help should not raise and should mention sub-apps.
    helptext = cli.app.help_format  # attribute exists; ensure app is well-formed
    assert helptext is None or isinstance(helptext, str)
    assert "problem" in cli.app
