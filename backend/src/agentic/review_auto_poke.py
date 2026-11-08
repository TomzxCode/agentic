"""Automatically poke the reviewers of the user's unreviewed pull requests.

The review nudge SLO tells the inbox when a pull request of the user's has
waited too long for anyone's review. This module turns that nudge into a
schedule: a setting of ages, counted from when a pull request was last marked
ready for review (or opened, when it never was), at which the app DMs its
requested reviewers without waiting to be asked.

The setting is a comma-separated list of durations. Each entry is an absolute
age counted from the pull request's review start (opened, or last marked ready).
The last entry may carry a repeat step; a repeat without ``~`` stays on the
SLO's own clock, and one with ``~`` waits that long after each poke::

    24h,26h,28h     pokes at 24h, 26h, and 28h, then stops
    24h+1h          pokes at 24h, then on the SLO's hourly boundaries
    24h+~1h         pokes at 24h, then every 1h after each poke
    now+1h          pokes now, then on the SLO's hourly boundaries
    now+~1h         pokes now, then every 1h after each poke
    next+1h         first poke at the next SLO boundary, then hourly boundaries
    next+~1h        first poke one interval from now, then every interval after each poke
    24h,24h+1h      the same as 24h+1h; a duplicate age is harmless

The rounds already delivered for each pull request live in ``ReviewAutoPoke``,
so a restart does not repeat a poke. A round missed while the app was down is
collapsed into the next one instead of firing a burst, and a change to the
schedule starts each pull request's rounds over.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlmodel import Session, col, select

from .models.base import utcnow
from .models.reviews import ReviewAutoPoke
from .my_pulls import fetch_my_pulls, known_github_repositories
from .refresh import parse_duration
from .review_messages import render_message
from .reviewer_pokes import poke_reviewers
from .settings_store import get_settings

log = structlog.get_logger(__name__)

#: Spellings of a schedule that mean the setting is off.
_OFF_VALUES = frozenset({"off", "never", "none", "-"})


@dataclass(frozen=True)
class PokeSchedule:
    """Absolute ages, plus an optional repeat that is aligned or poke-relative."""

    text: str
    ages: tuple[timedelta, ...]
    repeat: timedelta | None = None
    #: True: repeat on the SLO's own clock (start + n*step). False: wait the
    #: step after each poke.
    aligned: bool = True
    #: ``next+...``: there is no absolute age; the first poke is the next
    #: boundary after the schedule starts.
    next_boundary: bool = False

    def due(self, elapsed: timedelta) -> int:
        """How many absolute rounds have come due after ``elapsed``.

        The repeat is not counted here: whether it is aligned or relative to the
        last poke, it is evaluated from ``last_poked_at`` once the absolute
        rounds are delivered.
        """
        if self.next_boundary or not self.ages or elapsed < timedelta(0):
            return 0
        return sum(1 for age in self.ages if age <= elapsed)

    def age_for_round(self, round_number: int) -> timedelta | None:
        """The age at which the absolute ``round_number`` (one-based) is due."""
        if round_number < 1 or self.next_boundary or not self.ages:
            return None
        if self.repeat is None:
            return self.ages[round_number - 1] if round_number <= len(self.ages) else None
        finite = self.ages[:-1]
        if round_number <= len(finite):
            return finite[round_number - 1]
        base = self.ages[-1]
        return base + (round_number - len(finite) - 1) * self.repeat


def parse_auto_poke(value: str | None) -> PokeSchedule | None:
    """Parse the auto-poke setting, or None when it is off.

    Raises ``ValueError`` on a malformed schedule, with a message the settings
    endpoint returns to the user.
    """
    raw = (value or "").strip()
    if not raw or raw.lower() in _OFF_VALUES:
        return None
    tokens = [token.strip() for token in raw.split(",") if token.strip()]
    if not tokens:
        return None
    ages: list[timedelta] = []
    repeat: timedelta | None = None
    aligned = True
    next_boundary = False
    for index, token in enumerate(tokens):
        prefix, separator, rest = token.partition("+")
        prefix = prefix.strip().lower()
        rest = rest.strip()
        if separator:
            if index != len(tokens) - 1:
                raise ValueError(
                    "only the last entry may repeat; write 24h,26h,28h to stop, "
                    "or 24h+1h, now+1h, next+1h, now+~1h, next+~1h to keep poking"
                )
            entry_aligned = True
            step_text = rest
            if step_text.startswith("~"):
                entry_aligned = False
                step_text = step_text[1:].strip()
            step = parse_duration(step_text)
            if step is None:
                raise ValueError(f"'{token}' has no valid repeat step, such as 24h+1h or now+~1h")
            if prefix in ("now", "next"):
                if len(tokens) != 1:
                    raise ValueError(f"{prefix}+ must be the only entry")
                if prefix == "next":
                    next_boundary = True
                else:
                    ages.append(timedelta(0))
                repeat = step
                aligned = entry_aligned
                continue
            if prefix:
                base = parse_duration(prefix)
                if base is None:
                    raise ValueError(f"'{token}' is not a base age plus a repeat step, such as 24h+1h")
            elif ages:
                # A bare "+1h" after an age repeats from that age.
                base = ages[-1]
            else:
                # The old shorthand for a schedule that starts now. Keep it
                # relative to the last poke, the meaning it grew up with.
                ages.append(timedelta(0))
                repeat = step
                aligned = False
                continue
            if ages and base < ages[-1]:
                raise ValueError("ages must not decrease")
            repeat = step
            aligned = entry_aligned
            age = base
        else:
            if next_boundary:
                raise ValueError("next+ must be the only entry")
            age = parse_duration(token)
            if age is None:
                raise ValueError(f"'{token}' is not a duration such as 24h or 26h, or a repeating form such as now+1h")
            if ages and age < ages[-1]:
                raise ValueError("ages must not decrease")
        ages.append(age)
    unique: list[timedelta] = []
    for age in ages:
        if not unique or age != unique[-1]:
            unique.append(age)
    return PokeSchedule(
        text=raw,
        ages=tuple(unique),
        repeat=repeat,
        aligned=aligned,
        next_boundary=next_boundary,
    )


def _trigger_values(
    schedule: PokeSchedule,
    row: ReviewAutoPoke,
    reference: datetime,
    now: datetime,
) -> tuple[timedelta, timedelta]:
    """The SLO that triggered this poke, and the pull request's age."""
    if schedule.next_boundary:
        slo = schedule.repeat or timedelta(0)
    else:
        due = schedule.due(now - reference)
        if due > row.poked_rounds and schedule.ages:
            slo = schedule.ages[due - 1]
            # ``now+`` starts at absolute age zero; the interval the user
            # configured is the repeat, not a zero-length SLO.
            if slo == timedelta(0) and schedule.repeat is not None:
                slo = schedule.repeat
        else:
            slo = schedule.repeat or (schedule.ages[-1] if schedule.ages else timedelta(0))
    # The message always reports the age since the review start (opened or
    # last ready for review), even for a repeat round.
    return slo, now - reference


def _parse_instant(value: Any) -> datetime | None:
    """An ISO timestamp as aware UTC, or None when it cannot be read."""
    text = str(value or "").replace("Z", "+00:00")
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _pull_key(repository: str, number: int) -> str:
    return f"{repository.lower()}#{number}"


def _as_utc(value: datetime) -> datetime:
    """A stored timestamp as aware UTC (SQLite drops the zone)."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _reference_time(pull: dict[str, Any]) -> datetime | None:
    """When the pull request's current review round began.

    The latest ``ready_for_review`` timeline event is exact when the pull
    request spent time as a draft. A pull request opened ready has no such
    event, so its opening time is the fallback.
    """
    return _parse_instant(pull.get("ready_for_review_at")) or _parse_instant(pull.get("created_at"))


def _next_aligned(reference: datetime, step: timedelta, after: datetime) -> datetime:
    """The first start-anchored boundary strictly after ``after``."""
    if after < reference:
        return reference + step
    periods = (after - reference) // step
    return reference + (periods + 1) * step


def _first_poke_at(schedule: PokeSchedule, reference: datetime, current: datetime) -> datetime | None:
    """When a fresh schedule would next poke, before any poke is on record."""
    if schedule.next_boundary:
        if schedule.repeat is None:
            return None
        if schedule.aligned:
            return _next_aligned(reference, schedule.repeat, current)
        return max(current, reference) + schedule.repeat
    if schedule.due(current - reference) > 0:
        return current
    if not schedule.ages:
        return None
    return reference + schedule.ages[0]


def _following_poke_at(
    schedule: PokeSchedule,
    reference: datetime,
    row: ReviewAutoPoke,
    current: datetime,
) -> datetime | None:
    """When the next poke falls, from the rounds already on record."""
    if schedule.next_boundary:
        if schedule.repeat is None:
            return None
        if row.last_poked_at is None:
            anchor = _as_utc(row.anchor_at) if row.anchor_at else current
            if schedule.aligned:
                return _next_aligned(reference, schedule.repeat, anchor)
            return max(anchor, reference) + schedule.repeat
        last = _as_utc(row.last_poked_at)
        return _next_aligned(reference, schedule.repeat, last) if schedule.aligned else last + schedule.repeat
    if schedule.due(current - reference) > row.poked_rounds:
        return current
    if schedule.repeat is not None and row.last_poked_at is not None and row.poked_rounds >= len(schedule.ages):
        last = _as_utc(row.last_poked_at)
        return _next_aligned(reference, schedule.repeat, last) if schedule.aligned else last + schedule.repeat
    age = schedule.age_for_round(row.poked_rounds + 1)
    return reference + age if age is not None else None


def _round_due(schedule: PokeSchedule, row: ReviewAutoPoke, reference: datetime, now: datetime) -> bool:
    """Whether this tick should send a poke for the row's current rounds."""
    if schedule.next_boundary:
        if schedule.repeat is None:
            return False
        if row.last_poked_at is None:
            anchor = _as_utc(row.anchor_at) if row.anchor_at else now
            first = (
                _next_aligned(reference, schedule.repeat, anchor)
                if schedule.aligned
                else max(anchor, reference) + schedule.repeat
            )
            return now >= first
        last = _as_utc(row.last_poked_at)
        next_at = _next_aligned(reference, schedule.repeat, last) if schedule.aligned else last + schedule.repeat
        return now >= next_at
    if schedule.due(now - reference) > row.poked_rounds:
        return True
    if schedule.repeat is None or row.last_poked_at is None or row.poked_rounds < len(schedule.ages):
        return False
    last = _as_utc(row.last_poked_at)
    next_at = _next_aligned(reference, schedule.repeat, last) if schedule.aligned else last + schedule.repeat
    return now >= next_at


def _reset_row(row: ReviewAutoPoke, schedule: PokeSchedule, now: datetime) -> None:
    """Start a new schedule or review round from ``now``."""
    row.schedule = schedule.text
    row.poked_rounds = 0
    row.last_poked_at = None
    row.anchor_at = now
    row.updated_at = now


def run_auto_poke_once(session: Session) -> dict[str, int | str | None]:
    """Poke every pull request whose schedule has a round due.

    The list is the same read the My PRs page uses. A read that failed changes
    nothing, so a transient GitHub or ghx failure does not reset the rounds
    already delivered. Returns the number of reviewers reached and the number
    that could not be.
    """
    try:
        values = get_settings(session)
        schedule = parse_auto_poke(values.get("review_auto_poke", ""))
    except ValueError as exc:
        log.warning("review auto-poke setting is malformed", error=str(exc))
        return {"poked": 0, "failed": 0, "error": str(exc)}
    if schedule is None:
        return {"poked": 0, "failed": 0}

    message_template = values.get("review_auto_poke_message", "")
    login = str(values.get("github_login") or "").strip()
    report = fetch_my_pulls(login, known_github_repositories(session))
    if report.get("error"):
        return {"poked": 0, "failed": 0, "error": str(report["error"])}

    now = utcnow()
    candidates: dict[str, tuple[dict[str, Any], datetime, list[str]]] = {}
    for pull in report.get("pulls") or []:
        # ``fetch_my_pulls`` asks GitHub for open PRs, but check the state on
        # the row too: a cache entry can outlive a merge by a refresh.
        if str(pull.get("state") or "").upper() != "OPEN":
            continue
        if pull.get("draft") or pull.get("reviewed"):
            continue
        reviewers = [str(name).strip() for name in (pull.get("requested_reviewers") or []) if str(name).strip()]
        if not reviewers:
            continue
        reference = _reference_time(pull)
        if reference is None:
            continue
        repository = str(pull.get("repository") or "")
        number = int(pull.get("number") or 0)
        if not repository or number < 1:
            continue
        candidates[_pull_key(repository, number)] = (pull, reference, reviewers)

    rows = {_pull_key(row.repository, row.number): row for row in session.exec(select(ReviewAutoPoke)).all()}
    # Keep a row for a pull request that left the set. A read can omit a pull
    # request for a tick (a cold cache, a partially failed repository lookup),
    # and deleting its row would make it look unpoked when it returns, sending
    # the same round again. The row costs nothing while the pull request is not
    # a candidate, and a new ready-for-review round resets it below.

    poked = 0
    failed = 0
    for key, (pull, reference, reviewers) in candidates.items():
        row = rows.get(key)
        if row is None:
            row = ReviewAutoPoke(
                repository=str(pull.get("repository") or ""),
                number=int(pull.get("number") or 0),
                schedule=schedule.text,
                anchor_at=now,
            )
            # Persist a fresh row even when no round is due yet: next+ needs its
            # anchor to stay put while the job waits for the boundary.
            session.add(row)
            session.commit()
        elif row.schedule != schedule.text or (
            row.last_poked_at is not None and _as_utc(row.last_poked_at) < reference
        ):
            # A different schedule, or a new ready-for-review round since the
            # last poke, starts the cycle over from now.
            _reset_row(row, schedule, now)
            session.add(row)
            session.commit()
        if not _round_due(schedule, row, reference, now):
            continue
        url = str(pull.get("url") or "")
        title = str(pull.get("title") or "")
        slo, elapsed = _trigger_values(schedule, row, reference, now)
        message = render_message(message_template, url=url, title=title, slo=slo, elapsed=elapsed)
        outcome = poke_reviewers(session, url=url, title=title, logins=reviewers, message=message)
        if schedule.next_boundary:
            row.poked_rounds += 1
        else:
            row.poked_rounds = max(row.poked_rounds, schedule.due(now - reference))
        row.last_poked_at = now
        row.updated_at = now
        session.add(row)
        session.commit()
        poked += len(outcome.poked)
        failed += len(outcome.failed)
        log.info(
            "auto-poked pull request reviewers",
            repository=row.repository,
            number=row.number,
            round=row.poked_rounds,
            poked=len(outcome.poked),
            failed=len(outcome.failed),
        )
        for failure in outcome.failed:
            log.warning(
                "auto-poke could not reach a reviewer",
                repository=row.repository,
                number=row.number,
                login=failure.get("login"),
                reason=failure.get("reason"),
            )
    return {"poked": poked, "failed": failed}


def next_poke_at(
    session: Session,
    pull: dict[str, Any] | None,
    *,
    now: datetime | None = None,
) -> datetime | None:
    """When the auto-poke job will next DM this pull request's reviewers.

    ``pull`` is the My PRs row (``services.github.pull_row_from_record`` gives
    one from a ghx record). None when auto-poking is off, the pull request is
    not eligible (reviewed, draft, nobody requested, no date), or its schedule
    has no round left. A round already due comes back as ``now``, which the page
    can read as "due now".
    """
    if pull is None:
        return None
    try:
        values = get_settings(session)
        schedule = parse_auto_poke(values.get("review_auto_poke", ""))
    except ValueError:
        return None
    if schedule is None:
        return None
    # Auto-poke only covers the user's own pull requests; another author's PR
    # in the reviewers read is one they are reviewing, not one to nudge.
    login = str(values.get("github_login") or "").strip().lower()
    author = str(pull.get("author") or "").strip().lower()
    if not login or author != login:
        return None
    if str(pull.get("state") or "").upper() != "OPEN":
        return None
    if pull.get("draft") or pull.get("reviewed"):
        return None
    if not (pull.get("requested_reviewers") or []):
        return None
    reference = _reference_time(pull)
    if reference is None:
        return None
    repository = str(pull.get("repository") or "").strip().lower()
    number = int(pull.get("number") or 0)
    if not repository or number < 1:
        return None
    row = session.exec(
        select(ReviewAutoPoke).where(
            col(ReviewAutoPoke.repository) == repository,
            col(ReviewAutoPoke.number) == number,
        )
    ).first()
    current = now or utcnow()
    starts_over = (
        row is None
        or row.schedule != schedule.text
        or (row.last_poked_at is not None and _as_utc(row.last_poked_at) < reference)
    )
    next_at = (
        _first_poke_at(schedule, reference, current)
        if starts_over
        else _following_poke_at(schedule, reference, row, current)
    )
    if next_at is None:
        return None
    return next_at if next_at > current else current


__all__ = ["PokeSchedule", "next_poke_at", "parse_auto_poke", "run_auto_poke_once"]
