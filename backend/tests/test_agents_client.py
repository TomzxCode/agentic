"""The ACP client callbacks and the pure content-normalization helpers."""

from types import SimpleNamespace
from typing import cast

import pytest
from acp import Agent, RequestError
from acp.schema import AllowedOutcome, DeniedOutcome, ElicitationMode, PermissionOption, TextContentBlock

from agentic.agents.client import AgenticClient, _content_text, _dump


async def _noop(_event: dict) -> None:
    return None


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (SimpleNamespace(type="text", text="hello"), "hello"),
        (SimpleNamespace(type="image"), "[image]"),
        (SimpleNamespace(type="audio"), "[audio]"),
        (SimpleNamespace(type="resource_link", name="spec", uri="file:///spec.md"), "[spec](file:///spec.md)"),
        (SimpleNamespace(type="resource", resource=SimpleNamespace(text="body", uri="u")), "body"),
        (SimpleNamespace(type="resource", resource=SimpleNamespace(uri="u")), "[resource u]"),
        (SimpleNamespace(type="unknown"), ""),
    ],
)
def test_content_text_normalizes_each_kind(content, expected):
    assert _content_text(content) == expected


def test_dump_handles_none_and_models():
    assert _dump(None) == {}
    assert _dump(TextContentBlock(type="text", text="hi")) == {"type": "text", "text": "hi"}


@pytest.mark.asyncio
async def test_session_update_normalizes_each_kind():
    events: list[dict] = []

    async def publish(event: dict) -> None:
        events.append(event)

    client = AgenticClient(cwd=".", publish=publish)

    def chunk(kind: str, text: str) -> SimpleNamespace:
        return SimpleNamespace(session_update=kind, content=TextContentBlock(type="text", text=text))

    await client.session_update("s", chunk("agent_message_chunk", "hi"))
    await client.session_update("s", chunk("agent_thought_chunk", "th"))
    await client.session_update("s", chunk("user_message_chunk", "me"))
    await client.session_update("s", SimpleNamespace(session_update="tool_call", title="Bash"))
    await client.session_update("s", SimpleNamespace(session_update="tool_call_update", title="Bash done"))
    plan = SimpleNamespace(session_update="plan", entries=[TextContentBlock(type="text", text="step")])
    await client.session_update("s", plan)
    await client.session_update("s", SimpleNamespace(session_update="usage_update"))
    await client.session_update("s", SimpleNamespace(session_update="something_new"))

    assert [e["type"] for e in events] == [
        "message",
        "thought",
        "user",
        "tool_call",
        "tool_update",
        "plan",
        "usage",
        "info",
    ]
    # Sequence numbers are assigned in order for the transcript.
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))


@pytest.mark.asyncio
async def test_request_permission_auto_approves_an_allow_option():
    events: list[dict] = []

    async def publish(event: dict) -> None:
        events.append(event)

    client = AgenticClient(cwd=".", publish=publish, auto_approve=True)
    options = [
        PermissionOption(option_id="reject", name="Reject", kind="reject_once"),
        PermissionOption(option_id="ok", name="Allow", kind="allow_once"),
    ]
    response = await client.request_permission("s", SimpleNamespace(title="Bash"), options)
    assert isinstance(response.outcome, AllowedOutcome)
    assert response.outcome.option_id == "ok"
    assert events[0]["type"] == "permission"


@pytest.mark.asyncio
async def test_request_permission_falls_back_and_denies():
    client = AgenticClient(cwd=".", publish=_noop, auto_approve=True)
    # No allow option: the first option is used.
    only_reject = [PermissionOption(option_id="r", name="Reject", kind="reject_once")]
    allowed = await client.request_permission("s", SimpleNamespace(), only_reject)
    assert isinstance(allowed.outcome, AllowedOutcome) and allowed.outcome.option_id == "r"

    # No options at all with auto-approve on is denied.
    assert isinstance((await client.request_permission("s", SimpleNamespace(), [])).outcome, DeniedOutcome)

    # Auto-approve off is always denied.
    manual = AgenticClient(cwd=".", publish=_noop, auto_approve=False)
    deny = await manual.request_permission("s", SimpleNamespace(title="Bash"), only_reject)
    assert isinstance(deny.outcome, DeniedOutcome)


@pytest.mark.asyncio
async def test_read_and_write_text_files(tmp_path):
    (tmp_path / "f.txt").write_text("a\nb\nc\n")
    client = AgenticClient(cwd=str(tmp_path), publish=_noop)

    assert (await client.read_text_file("s", "f.txt")).content == "a\nb\nc\n"
    sliced = await client.read_text_file("s", "f.txt", line=2, limit=1)
    assert sliced.content == "b\n"

    written = await client.write_text_file("s", "sub/g.txt", "hello")
    assert written is not None
    assert (tmp_path / "sub" / "g.txt").read_text() == "hello"


@pytest.mark.asyncio
async def test_unsupported_methods_raise_method_not_found():
    client = AgenticClient(cwd=".", publish=_noop)
    calls = [
        client.create_terminal("s", "ls"),
        client.terminal_output("s", "t"),
        client.release_terminal("s", "t"),
        client.wait_for_terminal_exit("s", "t"),
        client.kill_terminal("s", "t"),
        client.create_elicitation("m", cast("ElicitationMode", "form")),
        client.ext_method("x", {}),
    ]
    for coro in calls:
        with pytest.raises(RequestError):
            await coro

    assert await client.complete_elicitation("e") is None
    assert client.on_connect(cast("Agent", None)) is None
    assert await client.ext_notification("x", {}) is None
