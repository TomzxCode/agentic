from datetime import timedelta

from sqlmodel import Session

from agentic import ghx_cache
from agentic.db import create_db_and_tables, engine
from agentic.models.system import Setting
from agentic.settings_store import GHX_CACHE_STATUS_KEY, get_ghx_cache_status, update_settings


def _clear_settings() -> None:
    """Drop the rows this file writes, so a later test starts from the defaults."""
    create_db_and_tables()
    with Session(engine) as session:
        for key in ("ghx_cache_refresh_interval", GHX_CACHE_STATUS_KEY):
            row = session.get(Setting, key)
            if row is not None:
                session.delete(row)
        session.commit()


def _no_refresh(*args, **kwargs):
    raise AssertionError("ghx cache ran when it should not have")


def test_cache_interval_parses_durations_and_off_spellings():
    assert ghx_cache.cache_interval("15m") == timedelta(minutes=15)
    assert ghx_cache.cache_interval("1h30m") == timedelta(minutes=90)
    assert ghx_cache.cache_interval("") is None
    assert ghx_cache.cache_interval("off") is None
    assert ghx_cache.cache_interval("not a duration") is None


def test_refresh_repositories_deltas_a_warm_cache_and_warms_a_cold_one(monkeypatch):
    calls: list[tuple[str, int]] = []

    def fake(owner, repo, timeout=300, types="both"):
        calls.append((f"{owner}/{repo}", timeout))
        return True

    monkeypatch.setattr(ghx_cache, "list_cached_repositories", lambda: {"o/r"})
    monkeypatch.setattr(ghx_cache, "refresh_github_cache", fake)
    ghx_cache._retry_after.clear()

    report = ghx_cache.refresh_repositories(["o/r", "o/s"])

    assert report == {"refreshed": 2, "failed": 0, "skipped": 0, "error": None}
    # A warmed cache takes the quick delta; a cold one walks its history here,
    # which is the one place allowed to wait for it.
    assert sorted(calls) == [("o/r", ghx_cache.DELTA_TIMEOUT), ("o/s", ghx_cache.WARM_TIMEOUT)]


def test_refresh_repositories_skips_the_pass_when_the_cache_listing_fails(monkeypatch):
    monkeypatch.setattr(ghx_cache, "list_cached_repositories", lambda: None)
    monkeypatch.setattr(ghx_cache, "refresh_github_cache", _no_refresh)
    ghx_cache._retry_after.clear()

    report = ghx_cache.refresh_repositories(["o/r"])

    assert report["refreshed"] == 0
    assert report["skipped"] == 1
    assert report["error"]


def test_refresh_repositories_backs_off_a_failed_repository(monkeypatch):
    monkeypatch.setattr(ghx_cache, "list_cached_repositories", lambda: {"o/r"})
    monkeypatch.setattr(ghx_cache, "refresh_github_cache", lambda *args, **kwargs: False)
    ghx_cache._retry_after.clear()

    assert ghx_cache.refresh_repositories(["o/r"])["failed"] == 1
    # The next pass leaves it alone instead of restarting a long walk right away.
    monkeypatch.setattr(ghx_cache, "refresh_github_cache", _no_refresh)
    report = ghx_cache.refresh_repositories(["o/r"])
    ghx_cache._retry_after.clear()

    assert report == {"refreshed": 0, "failed": 0, "skipped": 1, "error": None}


def test_run_due_ghx_cache_refresh_records_a_pass_then_waits_for_the_cadence(monkeypatch):
    monkeypatch.setattr(ghx_cache, "known_github_repositories", lambda session: ["o/r"])
    monkeypatch.setattr(ghx_cache, "list_cached_repositories", lambda: {"o/r"})
    monkeypatch.setattr(ghx_cache, "refresh_github_cache", lambda *args, **kwargs: True)
    ghx_cache._retry_after.clear()
    _clear_settings()

    try:
        with Session(engine) as session:
            update_settings(session, {"ghx_cache_refresh_interval": "15m"})
            first = ghx_cache.run_due_ghx_cache_refresh(session)
            status = get_ghx_cache_status(session)
            second = ghx_cache.run_due_ghx_cache_refresh(session)

        assert first == {"refreshed": 1, "failed": 0, "skipped": 0, "error": None}
        assert status["refreshed"] == 1
        assert status["origin"] == "background"
        assert second == {"skipped": "not-due"}
    finally:
        _clear_settings()


def test_run_due_ghx_cache_refresh_is_off_when_the_cadence_is_blank(monkeypatch):
    monkeypatch.setattr(ghx_cache, "refresh_github_cache", _no_refresh)
    _clear_settings()

    try:
        with Session(engine) as session:
            update_settings(session, {"ghx_cache_refresh_interval": ""})
            assert ghx_cache.run_due_ghx_cache_refresh(session) == {"skipped": "disabled"}
    finally:
        _clear_settings()
