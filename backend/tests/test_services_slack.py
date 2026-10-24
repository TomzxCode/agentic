"""Slack fetch helpers and thread naming."""

import threading
from datetime import UTC

import pytest

from agentic.services import shell, slack


def test_slack_timestamps_and_latest_message():
    # The newest message in a payload is the watermark a done thread compares to.
    payload = '{"messages": [{"ts": "1700000000.000100"}, {"ts": "1700000200.000000"}, {"ts": "bad"}, {}]}'
    assert slack.slack_latest_message_ts(payload) == "1700000200.000000"
    assert slack.slack_latest_message_ts('{"messages": []}') is None
    assert slack.slack_latest_message_ts("not json") is None
    assert slack.slack_latest_message_ts('{"messages": [{"ts": 1700000300}]}') == "1700000300"

    assert slack.slack_ts_after("1700000200.000000", "1700000100.000000") is True
    assert slack.slack_ts_after("1700000100.000000", "1700000100.000000") is False
    assert slack.slack_ts_after(None, "1700000100.000000") is False
    assert slack.slack_ts_after("nope", "1700000100.000000") is False

    moment = slack.slack_ts_datetime("1700000000.000000")
    assert moment is not None and moment.tzinfo is not None
    assert slack.slack_ts_datetime(None) is None
    assert slack.slack_ts_datetime("nope") is None


def test_fetch_slack_records_the_latest_message_timestamp(monkeypatch):
    def fake(cmd, timeout=60):
        if cmd[1:3] == ["conversations", "show"]:
            if "--json" in cmd:
                return '{"messages": [{"ts": "1700000000.000000"}, {"ts": "1700000500.000000"}]}'
            return "transcript"
        return None

    monkeypatch.setattr(shell, "_cli_available", lambda name: True)
    monkeypatch.setattr(shell, "_run_cli", fake)
    result: dict = {"title": "t", "content": "", "metadata": {}}
    slack._fetch_slack("https://acme.slack.com/archives/C1/p1700000000000000", result)
    assert result["metadata"]["latest_ts"] == "1700000500.000000"


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
    # The thread payload carries no channel_name; `channels get` resolves it.
    def fake(cmd, timeout=60):
        if cmd[1:3] == ["conversations", "show"]:
            return '{"messages": []}' if "--json" in cmd else "transcript"
        if cmd[1:3] == ["channels", "get"]:
            return '{"channel_count": 1, "channels": [{"id": "C1", "name": "test"}]}'
        return None

    monkeypatch.setattr(shell, "_cli_available", lambda name: True)
    monkeypatch.setattr(shell, "_run_cli", fake)
    result: dict = {"title": "", "content": "", "metadata": {}}
    slack._fetch_slack("https://acme.slack.com/archives/C1/p1700000000000000", result)
    assert result["title"] == f"acme - #test - {slack.slack_item_datetime('1700000000.000000')}"


def test_resolve_slack_channel_id_takes_an_id_or_resolves_a_name(monkeypatch):
    calls: list = []

    def fake(cmd, timeout=60):
        calls.append(cmd)
        return '{"channel_count": 1, "channels": [{"id": "C0893LXNXMJ"}]}'

    monkeypatch.setattr(shell, "_run_cli", fake)
    # An id is already the key: no slackx round trip.
    assert slack.resolve_slack_channel_id("C0893LXNXMJ") == "C0893LXNXMJ"
    assert calls == []
    # A configured "#name" or bare name is resolved through slackx.
    assert slack.resolve_slack_channel_id("#help-ml-infrastructure") == "C0893LXNXMJ"
    assert calls[0][:3] == ["slackx", "channels", "get"]
    assert slack.resolve_slack_channel_id("help-ml-infrastructure") == "C0893LXNXMJ"
    assert slack.resolve_slack_channel_id("  ") is None


def test_resolve_slack_channel_id_reports_an_unreadable_answer(monkeypatch):
    monkeypatch.setattr(shell, "_run_cli", lambda cmd, timeout=60: "not json")
    assert slack.resolve_slack_channel_id("#general") is None
    monkeypatch.setattr(shell, "_run_cli", lambda cmd, timeout=60: None)
    assert slack.resolve_slack_channel_id("#general") is None


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
    cached = '{"user_count": 1, "users": [{"id": "U0123ABCDEF", "real_name": "Tom Rochette"}]}'
    fetched = '{"user_count": 1, "users": [{"id": "U0COLDCOLD", "name": "ada"}]}'
    calls: list = []

    def fake(cmd, timeout=60):
        calls.append(cmd)
        if cmd[1:3] == ["users", "list"]:
            return cached
        if cmd[1:3] == ["users", "get"]:
            return fetched if cmd[3] == "U0COLDCOLD" else None
        return None

    monkeypatch.setattr(shell, "_run_cli", fake)
    # One bulk read names the cached ids; an id the cache lacks is fetched on its
    # own, and one slackx cannot fetch at all is left out.
    assert slack.resolve_slack_user_ids(["ada", "U0123ABCDEF", "U0COLDCOLD", "U9999ZZZZZZ"]) == {
        "U0123ABCDEF": "Tom Rochette",
        "U0COLDCOLD": "ada",
    }
    kinds = [(cmd[1], cmd[2]) for cmd in calls]
    # The bulk cache read comes first; the two per-id fetches run together, so
    # their order is not fixed.
    assert kinds[0] == ("users", "list")
    assert sorted(kinds[1:]) == [("users", "get"), ("users", "get")]

    # No Slack user ids: slackx is not called at all.
    calls.clear()
    assert slack.resolve_slack_user_ids(["ada", "ada@example.com"]) == {}
    assert calls == []


def test_uncached_slack_users_are_fetched_together(monkeypatch):
    """Each uncached id is a slackx subprocess wait, so they run at once."""
    barrier = threading.Barrier(2, timeout=5)
    monkeypatch.setattr(slack, "slack_user_names", lambda: {})

    def fetch(user_id):
        barrier.wait()
        return f"name {user_id}"

    monkeypatch.setattr(slack, "slack_user_name", fetch)
    assert slack.resolve_slack_user_ids(["U0123ABCDEF", "U0COLDCOLD"]) == {
        "U0123ABCDEF": "name U0123ABCDEF",
        "U0COLDCOLD": "name U0COLDCOLD",
    }


def test_slack_user_name_falls_back_to_the_login(monkeypatch):
    payload = '{"user_count": 1, "users": [{"id": "U0123ABCDEF", "name": "ada"}]}'
    monkeypatch.setattr(shell, "_run_cli", lambda cmd, timeout=60: payload)
    assert slack.slack_user_name("U0123ABCDEF") == "ada"
    # An id the payload does not describe (or a broken payload) resolves to None.
    assert slack.slack_user_name("U9999ZZZZZZ") is None
    monkeypatch.setattr(shell, "_run_cli", lambda cmd, timeout=60: "not json")
    assert slack.slack_user_name("U0123ABCDEF") is None


class _SlackResponse:
    """The minimal shape of a Slack Web API response."""

    status_code = 200

    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


def test_resolve_slack_user_id_prefers_an_id_alias(monkeypatch):
    def fail(cmd, timeout=60):
        raise AssertionError("an id alias needs no slackx read")

    monkeypatch.setattr(shell, "_run_cli", fail)
    assert slack.resolve_slack_user_id(["alice", "U0123ABCDEF"]) == "U0123ABCDEF"
    assert slack.resolve_slack_user_id(["alice@example.com"]) is None


def test_resolve_slack_user_id_matches_a_cached_handle(monkeypatch):
    payload = '{"users": [{"id": "U0HANDLE1", "name": "alice"}, {"id": "U0OTHER22", "name": "bob"}]}'
    monkeypatch.setattr(shell, "_run_cli", lambda cmd, timeout=60: payload)
    assert slack.resolve_slack_user_id(["alice"]) == "U0HANDLE1"
    assert slack.resolve_slack_user_id(["nobody"]) is None


def test_slack_send_dm_posts_to_the_user_with_the_configured_token(monkeypatch):
    from agentic.config import settings

    calls = {}

    def fake_post(url, data=None, headers=None, timeout=None):
        calls.update(url=url, data=data, headers=headers)
        return _SlackResponse({"ok": True, "ts": "1.2"})

    monkeypatch.setattr(settings, "slack_token", "xoxb-1")
    monkeypatch.setattr(settings, "slack_cookie", "")
    monkeypatch.setattr(settings, "slack_api_base_url", "https://slack.example/api")
    monkeypatch.setattr(slack.httpx, "post", fake_post)

    assert slack.slack_send_dm("U0123ABCDEF", "hi") == {"ok": True, "ts": "1.2"}
    assert calls["url"] == "https://slack.example/api/chat.postMessage"
    assert calls["data"] == {
        "channel": "U0123ABCDEF",
        "text": "hi",
        "unfurl_links": "true",
        "unfurl_media": "true",
    }
    assert calls["headers"] == {"Authorization": "Bearer xoxb-1"}


def test_slack_send_dm_can_turn_link_previews_off(monkeypatch):
    from agentic.config import settings

    calls = {}

    def fake_post(url, data=None, headers=None, timeout=None):
        calls.update(data=data)
        return _SlackResponse({"ok": True, "ts": "1.2"})

    monkeypatch.setattr(settings, "slack_token", "xoxb-1")
    monkeypatch.setattr(settings, "slack_cookie", "")
    monkeypatch.setattr(slack.httpx, "post", fake_post)

    slack.slack_send_dm("U0123ABCDEF", "hi", unfurl=False)
    assert calls["data"] == {
        "channel": "U0123ABCDEF",
        "text": "hi",
        "unfurl_links": "false",
        "unfurl_media": "false",
    }


def test_slack_send_dm_carries_the_cookie_for_a_web_token(monkeypatch):
    from agentic.config import settings

    calls = {}

    def fake_post(url, data=None, headers=None, timeout=None):
        calls.update(headers=headers)
        return _SlackResponse({"ok": True, "ts": "1.2"})

    monkeypatch.setattr(settings, "slack_token", "xoxc-1")
    monkeypatch.setattr(settings, "slack_cookie", "xoxd-2")
    monkeypatch.setattr(slack.httpx, "post", fake_post)

    slack.slack_send_dm("U0123ABCDEF", "hi")
    assert calls["headers"] == {"Authorization": "Bearer xoxc-1", "Cookie": "d=xoxd-2"}


def test_slack_send_dm_names_an_unusable_configuration(monkeypatch):
    from agentic.config import settings

    monkeypatch.setattr(settings, "slack_token", "")
    with pytest.raises(slack.SlackError, match="SLACK_TOKEN"):
        slack.slack_send_dm("U0123ABCDEF", "hi")

    monkeypatch.setattr(settings, "slack_token", "xoxc-1")
    monkeypatch.setattr(settings, "slack_cookie", "")
    with pytest.raises(slack.SlackError, match="SLACK_COOKIE"):
        slack.slack_send_dm("U0123ABCDEF", "hi")


def test_slack_send_dm_raises_the_slack_error(monkeypatch):
    from agentic.config import settings

    monkeypatch.setattr(settings, "slack_token", "xoxb-1")
    monkeypatch.setattr(settings, "slack_cookie", "")
    monkeypatch.setattr(
        slack.httpx,
        "post",
        lambda *a, **k: _SlackResponse({"ok": False, "error": "channel_not_found"}),
    )
    with pytest.raises(slack.SlackError, match="channel_not_found"):
        slack.slack_send_dm("U0123ABCDEF", "hi")
