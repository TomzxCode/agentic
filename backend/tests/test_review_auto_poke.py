from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete as sa_delete
from sqlmodel import Session, col, select

from agentic import review_auto_poke
from agentic.db import create_db_and_tables, engine
from agentic.models.reviews import ReviewAutoPoke
from agentic.review_auto_poke import parse_auto_poke, run_auto_poke_once
from agentic.review_messages import validate_message_template
from agentic.reviewer_pokes import PokeOutcome

NOW = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)
REPOSITORY = "auto-poke/r"


def _pull(**overrides):
    pull = {
        "repository": REPOSITORY,
        "number": 1,
        "title": "Add the thing",
        "url": "https://github.com/auto-poke/r/pull/1",
        "state": "OPEN",
        "draft": False,
        "reviewed": False,
        "created_at": (NOW - timedelta(hours=30)).isoformat(),
        "ready_for_review_at": None,
        "requested_reviewers": ["alice"],
    }
    pull.update(overrides)
    return pull


def _cleanup():
    with Session(engine) as session:
        session.exec(sa_delete(ReviewAutoPoke).where(col(ReviewAutoPoke.repository) == REPOSITORY))
        session.commit()


def _run(monkeypatch, pulls, *, setting="24h,26h,28h", message="", now=NOW):
    monkeypatch.setattr(
        review_auto_poke,
        "get_settings",
        lambda session: {
            "review_auto_poke": setting,
            "review_auto_poke_message": message,
            "github_login": "tomzx",
        },
    )
    monkeypatch.setattr(review_auto_poke, "known_github_repositories", lambda session: ["auto-poke/r"])
    monkeypatch.setattr(
        review_auto_poke,
        "fetch_my_pulls",
        lambda login, repositories: {"login": login, "pulls": pulls, "counts": {}, "error": None},
    )
    monkeypatch.setattr(review_auto_poke, "utcnow", lambda: now)
    calls: list[dict] = []

    def fake_poke(session, **kwargs):
        calls.append(kwargs)
        return PokeOutcome(poked=[{"login": "alice", "name": "Alice", "slack_user_id": "U1", "ts": "1"}])

    monkeypatch.setattr(review_auto_poke, "poke_reviewers", fake_poke)
    with Session(engine) as session:
        result = run_auto_poke_once(session)
    return result, calls


def test_a_finite_schedule_pokes_at_each_age_and_stops():
    schedule = parse_auto_poke("24h,26h,28h")
    assert schedule is not None
    assert schedule.due(timedelta(hours=23)) == 0
    assert schedule.due(timedelta(hours=24)) == 1
    assert schedule.due(timedelta(hours=25)) == 1
    assert schedule.due(timedelta(hours=26)) == 2
    assert schedule.due(timedelta(hours=28)) == 3
    assert schedule.due(timedelta(days=3)) == 3


def test_a_trailing_step_repeats_after_the_last_age():
    schedule = parse_auto_poke("24h+1h")
    assert schedule is not None
    assert schedule.due(timedelta(hours=23)) == 0
    assert schedule.due(timedelta(hours=24)) == 1
    assert schedule.due(timedelta(hours=25)) == 1
    assert schedule.due(timedelta(hours=30)) == 1

    # The form with the base repeated is the same schedule.
    repeated = parse_auto_poke("24h,24h+1h")
    assert repeated is not None
    assert repeated.due(timedelta(hours=25)) == 1

    # So is a lone step after an age: it repeats from that age.
    shorthand = parse_auto_poke("24h,+1h")
    assert shorthand is not None
    assert shorthand.due(timedelta(hours=25)) == 1


def test_a_lone_step_starts_immediately():
    schedule = parse_auto_poke("+24h")
    assert schedule is not None
    assert schedule.due(timedelta(0)) == 1
    assert schedule.due(timedelta(hours=23)) == 1
    assert schedule.due(timedelta(hours=24)) == 1
    assert schedule.due(timedelta(hours=48)) == 1

    # After an earlier age it repeats from that age.
    after = parse_auto_poke("12h,+24h")
    assert after is not None
    assert after.due(timedelta(hours=11)) == 0
    assert after.due(timedelta(hours=12)) == 1
    assert after.due(timedelta(hours=36)) == 1


def test_now_and_next_forms_parse():
    now = parse_auto_poke("now+1h")
    assert now is not None
    assert now.ages == (timedelta(0),)
    assert now.repeat == timedelta(hours=1)
    assert now.aligned is True
    assert now.next_boundary is False

    now_relative = parse_auto_poke("now+~1h")
    assert now_relative is not None
    assert now_relative.aligned is False

    next_aligned = parse_auto_poke("next+1h")
    assert next_aligned is not None
    assert next_aligned.ages == ()
    assert next_aligned.repeat == timedelta(hours=1)
    assert next_aligned.aligned is True
    assert next_aligned.next_boundary is True

    next_relative = parse_auto_poke("next+~1h")
    assert next_relative is not None
    assert next_relative.aligned is False
    assert next_relative.next_boundary is True

    # The old leading plus stays as the immediate, last-poke-relative form.
    legacy = parse_auto_poke("+1h")
    assert legacy is not None
    assert legacy.ages == (timedelta(0),)
    assert legacy.aligned is False


def test_age_for_round_walks_a_schedule():
    finite = parse_auto_poke("24h,26h,28h")
    assert finite is not None
    assert [finite.age_for_round(round) for round in (1, 2, 3, 4)] == [
        timedelta(hours=24),
        timedelta(hours=26),
        timedelta(hours=28),
        None,
    ]

    repeating = parse_auto_poke("24h+1h")
    assert repeating is not None
    assert [repeating.age_for_round(round) for round in (1, 2, 3)] == [
        timedelta(hours=24),
        timedelta(hours=25),
        timedelta(hours=26),
    ]

    immediate = parse_auto_poke("now+24h")
    assert immediate is not None
    assert [immediate.age_for_round(round) for round in (1, 2, 3)] == [
        timedelta(0),
        timedelta(hours=24),
        timedelta(hours=48),
    ]

    later = parse_auto_poke("next+1h")
    assert later is not None
    assert later.age_for_round(1) is None


def test_off_and_malformed_schedules():
    assert parse_auto_poke("") is None
    assert parse_auto_poke("off") is None
    for text in (
        "soon",
        "24h+1h,26h",
        "26h,24h",
        "24h+0m",
        "+",
        "+soon",
        "now+1h,26h",
        "next+1h,26h",
        "now+",
        "next+",
        "next+~",
        "24h+",
    ):
        try:
            parse_auto_poke(text)
        except ValueError:
            continue
        raise AssertionError(f"{text!r} should be rejected")


def test_message_template_variables():
    validate_message_template("")
    validate_message_template("Waiting {elapsed}; the SLO is {slo}. {link}")
    for text in ("{wat}", "{slo", "plain text {"):
        with pytest.raises(ValueError):
            validate_message_template(text)


def test_auto_poke_sends_one_round_then_waits_for_the_next(monkeypatch):
    create_db_and_tables()
    _cleanup()
    try:
        result, calls = _run(monkeypatch, [_pull()])
        assert result["poked"] == 1
        assert [call["logins"] for call in calls] == [["alice"]]

        # A second tick at the same age does not repeat the same round.
        result, calls = _run(monkeypatch, [_pull()])
        assert result["poked"] == 0
        assert calls == []

        with Session(engine) as session:
            row = session.exec(select(ReviewAutoPoke).where(ReviewAutoPoke.repository == REPOSITORY)).one()
            # The first sight at 30h had three ages due and collapses them into
            # this one poke.
            assert row.poked_rounds == 3
            assert row.last_poked_at is not None
    finally:
        _cleanup()


def test_auto_poke_renders_the_message_template(monkeypatch):
    create_db_and_tables()
    _cleanup()
    try:
        result, calls = _run(
            monkeypatch,
            [_pull()],
            setting="24h+1h",
            message="SLO {slo}; waited {elapsed}; {link}",
        )
        assert result["poked"] == 1
        assert calls[0]["message"] == ("SLO 1d; waited 1d 6h; <https://github.com/auto-poke/r/pull/1|Add the thing>")
    finally:
        _cleanup()


def test_auto_poke_message_elapsed_is_the_total_age_on_a_repeat(monkeypatch):
    create_db_and_tables()
    _cleanup()
    try:
        message = "SLO {slo}; age {elapsed}"
        _run(monkeypatch, [_pull()], setting="now+~1h", message=message, now=NOW)
        result, calls = _run(
            monkeypatch,
            [_pull()],
            setting="now+~1h",
            message=message,
            now=NOW + timedelta(hours=1),
        )
        assert result["poked"] == 1
        assert calls[0]["message"] == "SLO 1h; age 1d 7h"
    finally:
        _cleanup()


def test_auto_poke_counts_from_ready_for_review(monkeypatch):
    create_db_and_tables()
    _cleanup()
    try:
        pull = _pull(ready_for_review_at=(NOW - timedelta(hours=2)).isoformat())
        result, calls = _run(monkeypatch, [pull])
        assert result["poked"] == 0
        assert calls == []
    finally:
        _cleanup()


def test_auto_poke_skips_reviewed_draft_and_reviewerless_pull_requests(monkeypatch):
    create_db_and_tables()
    _cleanup()
    try:
        pulls = [
            _pull(number=1, reviewed=True),
            _pull(number=2, draft=True),
            _pull(number=3, requested_reviewers=[]),
        ]
        result, calls = _run(monkeypatch, pulls)
        assert result["poked"] == 0
        assert calls == []

        # A pull request that had a row and was reviewed since stops poking, but
        # keeps its delivered-rounds row so a read that briefly omits it does
        # not make it look unpoked when it returns.
        _run(monkeypatch, [_pull(number=1)])
        result, calls = _run(monkeypatch, [_pull(number=1, reviewed=True)])
        assert result["poked"] == 0
        assert calls == []
        with Session(engine) as session:
            row = session.exec(select(ReviewAutoPoke).where(ReviewAutoPoke.repository == REPOSITORY)).one()
            assert row.number == 1
            assert row.poked_rounds == 3
    finally:
        _cleanup()


def test_auto_poke_skips_a_closed_pull_request(monkeypatch):
    create_db_and_tables()
    _cleanup()
    try:
        for state in ("CLOSED", "MERGED"):
            result, calls = _run(monkeypatch, [_pull(state=state)])
            assert result["poked"] == 0
            assert calls == []
    finally:
        _cleanup()


def test_a_lone_step_pokes_a_fresh_pull_request_immediately(monkeypatch):
    create_db_and_tables()
    _cleanup()
    try:
        fresh = _pull(created_at=NOW.isoformat())
        result, calls = _run(monkeypatch, [fresh], setting="+24h")
        assert result["poked"] == 1
        assert len(calls) == 1
    finally:
        _cleanup()


def test_a_lone_hour_pokes_once_then_waits_an_hour(monkeypatch):
    create_db_and_tables()
    _cleanup()
    try:
        fresh = _pull(created_at=(NOW - timedelta(minutes=1)).isoformat())

        result, calls = _run(monkeypatch, [fresh], setting="+1h", now=NOW)
        assert result["poked"] == 1

        # A tick one minute later is still the same round.
        result, calls = _run(monkeypatch, [fresh], setting="+1h", now=NOW + timedelta(minutes=1))
        assert result["poked"] == 0
        assert calls == []

        # The next round comes one hour after the poke.
        result, calls = _run(monkeypatch, [fresh], setting="+1h", now=NOW + timedelta(hours=1))
        assert result["poked"] == 1
        assert len(calls) == 1
    finally:
        _cleanup()


def test_now_plus_one_hour_aligns_to_the_slo_start(monkeypatch):
    create_db_and_tables()
    _cleanup()
    try:
        # The SLO started 30h 30m ago, so its hourly boundaries fall at :30.
        pull = _pull(created_at=(NOW - timedelta(hours=30, minutes=30)).isoformat())

        result, calls = _run(monkeypatch, [pull], setting="now+1h", now=NOW)
        assert result["poked"] == 1

        # The next poke is the next start-aligned boundary, 30 minutes away.
        result, calls = _run(monkeypatch, [pull], setting="now+1h", now=NOW + timedelta(minutes=30))
        assert result["poked"] == 1
        result, calls = _run(monkeypatch, [pull], setting="now+1h", now=NOW + timedelta(minutes=40))
        assert result["poked"] == 0
    finally:
        _cleanup()


def test_now_plus_tilde_one_hour_counts_from_the_poke(monkeypatch):
    create_db_and_tables()
    _cleanup()
    try:
        pull = _pull(created_at=(NOW - timedelta(hours=30, minutes=30)).isoformat())

        result, calls = _run(monkeypatch, [pull], setting="now+~1h", now=NOW)
        assert result["poked"] == 1

        # Not the SLO's :30 boundary: a full hour after the poke.
        result, calls = _run(monkeypatch, [pull], setting="now+~1h", now=NOW + timedelta(minutes=30))
        assert result["poked"] == 0
        result, calls = _run(monkeypatch, [pull], setting="now+~1h", now=NOW + timedelta(hours=1))
        assert result["poked"] == 1
    finally:
        _cleanup()


def test_next_plus_one_hour_waits_for_the_next_slo_boundary(monkeypatch):
    create_db_and_tables()
    _cleanup()
    try:
        pull = _pull(created_at=(NOW - timedelta(hours=30, minutes=30)).isoformat())

        result, calls = _run(monkeypatch, [pull], setting="next+1h", now=NOW)
        assert result["poked"] == 0
        result, calls = _run(monkeypatch, [pull], setting="next+1h", now=NOW + timedelta(minutes=29))
        assert result["poked"] == 0
        result, calls = _run(monkeypatch, [pull], setting="next+1h", now=NOW + timedelta(minutes=30))
        assert result["poked"] == 1
        result, calls = _run(monkeypatch, [pull], setting="next+1h", now=NOW + timedelta(hours=1))
        assert result["poked"] == 0
    finally:
        _cleanup()


def test_next_plus_tilde_one_hour_waits_one_interval_then_follows_pokes(monkeypatch):
    create_db_and_tables()
    _cleanup()
    try:
        pull = _pull(created_at=(NOW - timedelta(hours=30, minutes=30)).isoformat())

        result, calls = _run(monkeypatch, [pull], setting="next+~1h", now=NOW)
        assert result["poked"] == 0
        result, calls = _run(monkeypatch, [pull], setting="next+~1h", now=NOW + timedelta(minutes=59))
        assert result["poked"] == 0
        result, calls = _run(monkeypatch, [pull], setting="next+~1h", now=NOW + timedelta(hours=1))
        assert result["poked"] == 1
        result, calls = _run(monkeypatch, [pull], setting="next+~1h", now=NOW + timedelta(hours=1, minutes=30))
        assert result["poked"] == 0
        result, calls = _run(monkeypatch, [pull], setting="next+~1h", now=NOW + timedelta(hours=2))
        assert result["poked"] == 1
    finally:
        _cleanup()


def test_24h_tilde_one_hour_counts_from_the_catch_up_poke(monkeypatch):
    create_db_and_tables()
    _cleanup()
    try:
        pull = _pull(created_at=(NOW - timedelta(hours=30, minutes=30)).isoformat())

        result, calls = _run(monkeypatch, [pull], setting="24h+~1h", now=NOW)
        assert result["poked"] == 1
        result, calls = _run(monkeypatch, [pull], setting="24h+~1h", now=NOW + timedelta(minutes=30))
        assert result["poked"] == 0
        result, calls = _run(monkeypatch, [pull], setting="24h+~1h", now=NOW + timedelta(hours=1))
        assert result["poked"] == 1
    finally:
        _cleanup()


def test_a_repeat_does_not_burst_after_downtime(monkeypatch):
    create_db_and_tables()
    _cleanup()
    try:
        result, calls = _run(monkeypatch, [_pull()], setting="24h+~1h")
        assert result["poked"] == 1

        # The app was down for six hours. The next tick sends one poke, not six,
        # and the next round is one interval after it.
        result, calls = _run(monkeypatch, [_pull()], setting="24h+~1h", now=NOW + timedelta(hours=6))
        assert result["poked"] == 1
        assert len(calls) == 1
        with Session(engine) as session:
            row = session.exec(select(ReviewAutoPoke).where(ReviewAutoPoke.repository == REPOSITORY)).one()
            assert row.poked_rounds == 1
    finally:
        _cleanup()


def test_a_new_ready_round_starts_the_pokes_over(monkeypatch):
    create_db_and_tables()
    _cleanup()
    try:
        # Deliver the old round's reminders.
        _run(monkeypatch, [_pull()], setting="1h")
        with Session(engine) as session:
            row = session.exec(select(ReviewAutoPoke).where(ReviewAutoPoke.repository == REPOSITORY)).one()
            row.last_poked_at = NOW - timedelta(hours=3)
            session.add(row)
            session.commit()

        # The pull request was marked ready again after the last poke, so its
        # old rounds no longer count against the new one.
        pull = _pull(ready_for_review_at=(NOW - timedelta(hours=2)).isoformat())
        result, calls = _run(monkeypatch, [pull], setting="1h")
        assert result["poked"] == 1
        assert len(calls) == 1
    finally:
        _cleanup()


def test_a_changed_schedule_starts_the_rounds_over(monkeypatch):
    create_db_and_tables()
    _cleanup()
    try:
        _run(monkeypatch, [_pull()], setting="24h,26h,28h")
        result, calls = _run(monkeypatch, [_pull()], setting="12h,24h")
        assert result["poked"] == 1
        assert len(calls) == 1
        with Session(engine) as session:
            row = session.exec(select(ReviewAutoPoke).where(ReviewAutoPoke.repository == REPOSITORY)).one()
            assert row.schedule == "12h,24h"
            assert row.poked_rounds == 2
    finally:
        _cleanup()


def test_a_failed_read_leaves_the_delivered_rounds_alone(monkeypatch):
    create_db_and_tables()
    _cleanup()
    try:
        _run(monkeypatch, [_pull()])
        monkeypatch.setattr(review_auto_poke, "get_settings", lambda session: {"review_auto_poke": "24h,26h,28h"})
        monkeypatch.setattr(
            review_auto_poke,
            "fetch_my_pulls",
            lambda login, repositories: {"login": login, "pulls": [], "counts": {}, "error": "ghx is not installed"},
        )
        with Session(engine) as session:
            result = run_auto_poke_once(session)
        assert result["error"] == "ghx is not installed"
        with Session(engine) as session:
            assert len(session.exec(select(ReviewAutoPoke)).all()) == 1
    finally:
        _cleanup()
