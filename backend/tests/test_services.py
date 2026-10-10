from agentic.services import extract_context_json, infer_item_source, looks_like_url

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


def test_infer_item_source_from_value():
    github = infer_item_source("https://github.com/psf/requests/issues/1")
    assert github == {"source": "github", "kind": "issue", "external_id": "psf/requests#1"}

    pull = infer_item_source("https://github.com/psf/requests/pull/2")
    assert pull["source"] == "github" and pull["kind"] == "pull_request"

    slack = infer_item_source("https://acme.slack.com/archives/C123/p1700000000000000")
    assert slack["source"] == "slack" and slack["kind"] == "thread" and slack["external_id"] == "C123:1700000000000000"

    drive = infer_item_source("https://docs.google.com/document/d/AbC-123_x/edit")
    assert drive["source"] == "gdrive" and drive["external_id"] == "AbC-123_x"

    assert infer_item_source("https://example.com/page")["source"] == "url"
    assert infer_item_source(None, None, "some pasted text")["source"] == "note"
    assert infer_item_source("", None, "")["source"] == "note"
    # Plain text pasted where a URL is expected is a note, not a url.
    assert infer_item_source("User doesn't know what they want.")["source"] == "note"
    assert infer_item_source("just a reminder")["source"] == "note"


def test_looks_like_url():
    assert looks_like_url("https://github.com/o/r/issues/1")
    assert looks_like_url("github.com/o/r/issues/1")
    assert looks_like_url("example.com/page")
    assert not looks_like_url("User doesn't know what they want.")
    assert not looks_like_url("just a reminder")
    assert not looks_like_url("")
    assert not looks_like_url(None)
