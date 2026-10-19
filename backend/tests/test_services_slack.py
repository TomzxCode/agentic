"""Slack fetch helpers and thread naming."""

from datetime import UTC

from agentic.services import shell, slack


def test_fetch_slack_refreshes_with_fetch_then_reads_participants(monkeypatch):
    calls: list = []

    def fake(cmd, timeout=60):
        calls.append(cmd)
        if cmd[1:3] == ["conversations", "show"]:
            return "transcript" if "--json" not in cmd else '{"channel_name": "general", "messages": []}'
        return None

    monkeypatch.setattr(shell, "_cli_available", lambda name: True)
    monkeypatch.setattr(shell, "_run_cli", fake)
    result: dict = {"title": "t", "content": "", "metadata": {}}
    slack._fetch_slack("https://acme.slack.com/archives/C1/p1700000000000000", result)
    assert result["content"] == "transcript"
    assert result["metadata"]["channel"] == "C1"
    # A Slack thread is named after its organization, channel, and datetime.
    assert result["title"] == f"acme - #general - {slack.slack_item_datetime('1700000000.000000')}"
    assert result.get("error") is None
    # Both conversation reads are `show`: the transcript forces a refresh with
    # --fetch, and the participants read comes from the refreshed cache (no
    # second fetch). Names come from `users list`.
    assert [(cmd[1], cmd[2]) for cmd in calls] == [
        ("conversations", "show"),
        ("conversations", "show"),
        ("users", "list"),
    ]
    assert "--fetch" in calls[0]
    assert "--json" in calls[1] and "--fetch" not in calls[1]

    # No slackx output: the item still gets its metadata and a name, but the
    # refresh is reported as a failure so it does not read as success.
    result = {"title": "t", "content": "", "metadata": {}}
    monkeypatch.setattr(shell, "_run_cli", lambda cmd, timeout=60: None)
    slack._fetch_slack("https://acme.slack.com/archives/C1/p1700000000000000", result)
    assert result["content"] == "" and result["metadata"]["channel"] == "C1"
    assert result["title"] == f"acme - C1 - {slack.slack_item_datetime('1700000000.000000')}"
    assert result["error"] == "slackx could not fetch the Slack thread"


def test_fetch_slack_reports_a_missing_slackx(monkeypatch):
    monkeypatch.setattr(shell, "_cli_available", lambda name: False)
    result: dict = {"title": "", "content": "", "metadata": {}}
    slack._fetch_slack("https://acme.slack.com/archives/C1/p1700000000000000", result)
    assert result["error"] == "slackx is not installed; install it to fetch Slack threads"
    # The item is still named from its URL, even without slackx.
    assert result["title"] == f"acme - C1 - {slack.slack_item_datetime('1700000000.000000')}"


def test_failed_slack_fetch_keeps_a_resolved_channel_name(monkeypatch):
    monkeypatch.setattr(shell, "_cli_available", lambda name: True)
    monkeypatch.setattr(shell, "_run_cli", lambda cmd, timeout=60: None)
    # The stored title already carries the channel name; a later failed fetch
    # must not revert it to the channel id.
    result: dict = {
        "title": "acme - #general - 2023-11-14 22:13",
        "content": "",
        "metadata": {},
    }
    slack._fetch_slack("https://acme.slack.com/archives/C1/p1700000000000000", result)
    assert result["error"] == "slackx could not fetch the Slack thread"
    assert result["title"] == f"acme - #general - {slack.slack_item_datetime('1700000000.000000')}"


def test_fetch_slack_resolves_an_uncached_channel_name(monkeypatch):
    # The thread payload carries no channel_name; `channels list` resolves it.
    def fake(cmd, timeout=60):
        if cmd[1:3] == ["conversations", "show"]:
            return '{"messages": []}' if "--json" in cmd else "transcript"
        if cmd[1:3] == ["channels", "list"]:
            return '{"channel_count": 1, "channels": [{"id": "C1", "name": "test"}]}'
        return None

    monkeypatch.setattr(shell, "_cli_available", lambda name: True)
    monkeypatch.setattr(shell, "_run_cli", fake)
    result: dict = {"title": "", "content": "", "metadata": {}}
    slack._fetch_slack("https://acme.slack.com/archives/C1/p1700000000000000", result)
    assert result["title"] == f"acme - #test - {slack.slack_item_datetime('1700000000.000000')}"


def test_slack_naming_helpers():
    assert slack.slack_item_datetime("1700000000.000000", tz=UTC) == "2023-11-14 22:13"
    # A bad timestamp falls back to the raw value rather than raising.
    assert slack.slack_item_datetime("nope") == "nope"

    assert slack.slack_channel_label("C1", "general") == "#general"
    assert slack.slack_channel_label("C1", "#general") == "#general"
    assert slack.slack_channel_label("C1", "") == "C1"
    # A direct message keeps its bare name, with no channel prefix.
    assert slack.slack_channel_label("D1", "alice") == "alice"

    parsed = {"workspace": "acme", "channel": "C1", "ts": "1700000000.000000"}
    assert slack.slack_item_title(parsed, "general", tz=UTC) == "acme - #general - 2023-11-14 22:13"
    assert slack.slack_item_title(parsed, tz=UTC) == "acme - C1 - 2023-11-14 22:13"

    assert slack.slack_channel_name('{"channel_name": "general"}') == "general"
    # A payload without a channel name (or not JSON) resolves to None.
    assert slack.slack_channel_name("no json") is None
    assert slack.slack_channel_name('{"messages": []}') is None

    # A title already naming the channel is not downgraded to the bare id, and
    # a bare-id title is not mistaken for a name (no "#C1").
    assert slack.slack_title_channel("acme - #general - 2023-11-14 22:13", "acme") == "#general"
    assert slack.slack_title_channel("acme - C1 - 2023-11-14 22:13", "acme") == "C1"
    assert slack.slack_title_channel("acme - alice - 2023-11-14 22:13", "acme") == "alice"
    # A user-edited title, another workspace, or a non-title is not our format.
    assert slack.slack_title_channel("My own name", "acme") is None
    assert slack.slack_title_channel("other - #general - 2023-11-14 22:13", "acme") is None
    assert slack.slack_item_title(parsed, "C1", tz=UTC) == "acme - C1 - 2023-11-14 22:13"


def test_resolve_slack_channel_name(monkeypatch):
    monkeypatch.setattr(
        shell,
        "_run_cli",
        lambda cmd, timeout=60: '{"channel_count": 1, "channels": [{"id": "C1", "name": "test"}]}',
    )
    assert slack.resolve_slack_channel_name("C1") == "test"
    monkeypatch.setattr(shell, "_run_cli", lambda cmd, timeout=60: None)
    assert slack.resolve_slack_channel_name("C1") is None
    monkeypatch.setattr(shell, "_run_cli", lambda cmd, timeout=60: "not json")
    assert slack.resolve_slack_channel_name("C1") is None
    monkeypatch.setattr(shell, "_run_cli", lambda cmd, timeout=60: '{"channels": []}')
    assert slack.resolve_slack_channel_name("C1") is None


def test_is_slack_user_id():
    assert slack.is_slack_user_id("U0123ABCDEF")
    # A handle, an email, and a channel id are not user ids.
    assert not slack.is_slack_user_id("ada")
    assert not slack.is_slack_user_id("ada@example.com")
    assert not slack.is_slack_user_id("C0123ABCDEF")
    # Too short to be a Slack user id, so a plain alias starting with U is kept.
    assert not slack.is_slack_user_id("U123")


def test_resolve_slack_user_ids(monkeypatch):
    payload = '{"users": [{"id": "U0123ABCDEF", "real_name": "Tom Rochette"}]}'
    monkeypatch.setattr(shell, "_run_cli", lambda cmd, timeout=60: payload if cmd[1:3] == ["users", "list"] else None)
    # A resolve reads slackx once and names only the ids it knows.
    assert slack.resolve_slack_user_ids(["ada", "U0123ABCDEF", "U9999ZZZZZZ"]) == {"U0123ABCDEF": "Tom Rochette"}

    # No Slack user ids: slackx is not called at all.
    calls: list = []
    monkeypatch.setattr(shell, "_run_cli", lambda cmd, timeout=60: calls.append(cmd))
    assert slack.resolve_slack_user_ids(["ada", "ada@example.com"]) == {}
    assert calls == []
