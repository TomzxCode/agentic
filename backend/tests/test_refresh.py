"""The tiered refresh policy: parsing, band selection, and the due calculation."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from agentic.refresh import (
    PolicyError,
    as_utc,
    describe_policy,
    interval_for_age,
    is_due,
    item_age,
    item_start,
    parse_duration,
    parse_policy,
    policies_from_settings,
)

NOW = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)


def test_parse_policy_reads_bands_and_fallback():
    policy = parse_policy("1d=1h,7d=6h,30d=1d,*=7d")
    assert [tier.max_age for tier in policy.tiers] == [
        timedelta(days=1),
        timedelta(days=7),
        timedelta(days=30),
    ]
    assert [tier.interval for tier in policy.tiers] == [
        timedelta(hours=1),
        timedelta(hours=6),
        timedelta(days=1),
    ]
    assert policy.fallback == timedelta(days=7)
    assert policy.enabled


def test_empty_policy_is_disabled():
    policy = parse_policy("")
    assert not policy.tiers and policy.fallback is None
    assert not policy.enabled


def test_never_fallback_stops_refresh():
    policy = parse_policy("1d=1h,*=never")
    assert policy.fallback is None
    assert interval_for_age(policy, timedelta(days=2)) is None


@pytest.mark.parametrize("text", ["7d=1h,1d=2h", "1d", "1d=soon", "*=1h,*=2h", "1d=1h,1d=2h"])
def test_malformed_policies_raise(text):
    with pytest.raises(PolicyError):
        parse_policy(text)


def test_interval_for_age_selects_the_band():
    policy = parse_policy("1d=1h,7d=6h,30d=1d,*=7d")
    assert interval_for_age(policy, timedelta(hours=2)) == timedelta(hours=1)
    assert interval_for_age(policy, timedelta(days=3)) == timedelta(hours=6)
    assert interval_for_age(policy, timedelta(days=10)) == timedelta(days=1)
    assert interval_for_age(policy, timedelta(days=60)) == timedelta(days=7)


def test_interval_for_age_without_fallback_is_none_past_the_last_band():
    policy = parse_policy("1d=1h,7d=6h")
    assert interval_for_age(policy, timedelta(days=30)) is None


def test_is_due_uses_age_band_and_last_fetch():
    policy = parse_policy("1d=1h,30d=1d")
    age = timedelta(hours=2)  # hourly band
    assert is_due(policy, age=age, fetched_at=None, now=NOW) is True
    assert is_due(policy, age=age, fetched_at=NOW - timedelta(minutes=30), now=NOW) is False
    assert is_due(policy, age=age, fetched_at=NOW - timedelta(hours=2), now=NOW) is True
    # Past the last band with no fallback, never due even if never fetched.
    assert is_due(policy, age=timedelta(days=40), fetched_at=None, now=NOW) is False


def test_is_due_treats_naive_fetch_time_as_utc():
    policy = parse_policy("1d=1h")
    naive = (NOW - timedelta(hours=2)).replace(tzinfo=None)
    assert is_due(policy, age=timedelta(hours=1), fetched_at=naive, now=NOW) is True


def test_parse_duration_units():
    assert parse_duration("30m") == timedelta(minutes=30)
    assert parse_duration("2w") == timedelta(weeks=2)
    assert parse_duration("1.5h") == timedelta(minutes=90)
    assert parse_duration("soon") is None


def test_item_start_prefers_github_created_at():
    recorded = NOW - timedelta(days=90)
    item = SimpleNamespace(
        source="github",
        url="https://github.com/o/r/issues/1",
        metadata_json={"created_at": "2020-01-02T03:04:05Z"},
        created_at=recorded,
    )
    assert item_start(item) == datetime(2020, 1, 2, 3, 4, 5, tzinfo=UTC)
    assert item_age(item, NOW) > timedelta(days=300)


def test_item_start_reads_slack_thread_timestamp():
    item = SimpleNamespace(
        source="slack",
        url="https://team.slack.com/archives/C123/p1600000000000000",
        metadata_json={},
        created_at=NOW,
    )
    assert item_start(item) == datetime.fromtimestamp(1600000000, tz=UTC)


def test_item_start_falls_back_to_recorded_time():
    recorded = NOW - timedelta(days=2)
    item = SimpleNamespace(source="github", url=None, metadata_json={}, created_at=recorded)
    assert item_start(item) == as_utc(recorded)


def test_policies_from_settings_maps_sources_to_keys():
    effective = {"slack_refresh_policy": "1d=1h", "github_refresh_policy": "1d=2h"}
    assert policies_from_settings(effective) == {"slack": "1d=1h", "github": "1d=2h"}
    assert policies_from_settings({}) == {"slack": "", "github": ""}


def test_describe_policy_reports_bands():
    described = describe_policy("1d=1h,*=7d")
    assert described["valid"] and described["enabled"]
    assert described["tiers"] == [{"max_age_seconds": 86400, "interval_seconds": 3600}]
    assert described["fallback_seconds"] == 604800

    with pytest.raises(PolicyError):
        describe_policy("nope")
