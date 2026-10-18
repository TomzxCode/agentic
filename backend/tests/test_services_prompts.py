"""Context prompt building and JSON extraction."""

from agentic.services import prompts


def test_build_context_prompt_includes_repositories_worktrees_and_items():
    prompt = prompts.build_context_prompt(
        {
            "title": "T",
            "description": "D",
            "status": "open",
            "priority": 1,
            "repositories": ["/r/a"],
            "worktrees": [{"branch": "b", "path": "/w"}],
            "group": None,
        },
        [{"source": "note", "title": "n", "url": None, "content": "c"}],
    )
    assert "## Description" in prompt and "D" in prompt
    assert "## Repositories" in prompt and "/r/a" in prompt
    assert "## Active worktrees" in prompt and "b at /w" in prompt
    assert "[note] n" in prompt


def test_iter_json_objects_respects_strings_and_braces():
    text = '{"a": "}{"} trailing {"b": 2}'
    assert list(prompts._iter_json_objects(text)) == ['{"a": "}{"}', '{"b": 2}']


def test_repair_truncated_json_closes_open_structures():
    assert prompts._repair_truncated_json('{"a": "unterminated') == '{"a": "unterminated"}'
    assert prompts._repair_truncated_json('{"a": 1}') is None


def test_extract_context_json_coerces_string_steps():
    data = prompts.extract_context_json('{"summary": "s", "next_steps": ["do a", {"text": "do b", "done": true}]}')
    assert data is not None
    assert data["next_steps"] == [{"text": "do a", "done": False}, {"text": "do b", "done": True}]
