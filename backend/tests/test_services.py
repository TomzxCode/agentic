from agentic.services import extract_context_json

VALID = (
    '{"summary": "Do the thing.", "next_steps": '
    '[{"text": "Step one", "done": false}, {"text": "Step two", "done": true}]}'
)


def test_extracts_clean_json():
    data = extract_context_json(VALID)
    assert data is not None
    assert data["summary"] == "Do the thing."
    assert data["next_steps"] == [
        {"text": "Step one", "done": False},
        {"text": "Step two", "done": True},
    ]


def test_extracts_json_from_surrounding_prose():
    data = extract_context_json(f"Sure, here you go:\n{VALID}\nHope that helps!")
    assert data is not None
    assert data["summary"] == "Do the thing."


def test_extracts_json_from_code_fence():
    data = extract_context_json(f"```json\n{VALID}\n```")
    assert data is not None and data["summary"] == "Do the thing."


def test_repairs_truncated_json():
    truncated = '{"summary": "Cut off here", "next_steps": [{"text": "One", "done": false}'
    data = extract_context_json(truncated)
    assert data is not None
    assert data["summary"] == "Cut off here"
    assert data["next_steps"][0]["text"] == "One"


def test_ignores_braces_in_thoughts_when_only_json_present():
    data = extract_context_json("note {not json} then " + VALID)
    assert data is not None and data["summary"] == "Do the thing."


def test_returns_none_without_summary():
    assert extract_context_json('{"foo": "bar"}') is None
    assert extract_context_json("no json here") is None
