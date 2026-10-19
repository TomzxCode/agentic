"""The PR-feedback queue: reviewer comments awaiting a decision, from the store.

``handle-pr-reviewer-feedback`` writes one analysis file per reviewer comment on
the pull requests you authored, under the user-global ``~/.sdlc`` store. This
router reads those files as a triage queue and records an implement / decline /
defer decision back into a file, the same contract the skill and its executor
consume. The decision, not this app, is what queues the follow-up work.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..config import settings
from ..feedback_store import FeedbackItem, discover_feedback, find_feedback, parse_feedback, write_decision
from ..models.base import utcnow
from ..review_queue import enrich_from_github
from ..schemas.feedback import FeedbackDecisionUpdate, FeedbackItemRead, FeedbackListRead

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


def _item_key(item: FeedbackItem) -> tuple[str, str, int] | None:
    """A feedback item's pull request as (owner, repo, number), or None.

    A store keyed by the repository name alone has no owner, and ghx needs one,
    so such an item keeps an unknown PR state rather than a wrong fetch.
    """
    owner, _, repo = item.repo.partition("/")
    if not owner or not repo or not item.pr.isdigit():
        return None
    return (owner.lower(), repo.lower(), int(item.pr))


def _pr_states(items: list[FeedbackItem], refresh: bool) -> dict[tuple[str, str, int], str]:
    """Map each item's (owner, repo, number) to its GitHub state.

    ghx is the source of truth for a pull request's own state, and the lookups
    are cached for a short time inside ``enrich_from_github`` (a Refresh bypasses
    the cache). A lookup that fails leaves the state unknown rather than dropping
    the item, so the queue still renders without GitHub.
    """
    rows: list[dict] = []
    seen: set[tuple[str, str, int]] = set()
    for item in items:
        key = _item_key(item)
        if key is None or key in seen:
            continue
        seen.add(key)
        rows.append({"owner": key[0], "name": key[1], "number": key[2]})
    if not rows:
        return {}
    enrich_from_github(rows, refresh=refresh)
    # ghx reports OPEN / CLOSED / MERGED; the view only needs open vs closed.
    return {
        (row["owner"], row["name"], row["number"]): (
            "open" if str(row.get("state") or "").upper() == "OPEN" else "closed"
        )
        for row in rows
        if row.get("state")
    }


def _read(item: FeedbackItem, state: str) -> FeedbackItemRead:
    """An analysis file as the view reads it, with its derived state filled in."""
    pr_url = f"https://github.com/{item.repo}/pull/{item.pr}" if item.repo and item.pr else ""
    return FeedbackItemRead(
        feedback_id=item.feedback_id,
        kind=item.kind,
        repo=item.repo,
        pr=item.pr,
        author=item.author,
        created_at=item.created_at,
        head_commit=item.head_commit,
        analyzed_at=item.analyzed_at,
        recommendation=item.recommendation,
        confidence=item.confidence,
        session_link=item.session_link,
        decision=item.decision,
        decided_at=item.decided_at,
        executed_at=item.executed_at,
        title=item.title,
        path=item.path,
        sections=item.sections,
        status=item.status,
        run_state=item.run_state,
        state=state,
        pr_url=pr_url,
    )


def _state_for(states: dict[tuple[str, str, int], str], item: FeedbackItem) -> str:
    key = _item_key(item)
    return states.get(key, "") if key is not None else ""


def _counts(items: list[FeedbackItemRead]) -> dict[str, int]:
    counts = {"pending": 0, "implement": 0, "decline": 0, "defer": 0, "to_run": 0}
    for item in items:
        counts[item.status] = counts.get(item.status, 0) + 1
        if item.run_state == "awaiting":
            counts["to_run"] += 1
    return counts


@router.get("", response_model=FeedbackListRead)
def list_feedback(refresh: bool = False) -> FeedbackListRead:
    """Every reviewer-feedback file in the store, with its decision state.

    ``refresh`` re-reads each pull request's state from GitHub instead of the
    short ghx cache, the same way the review queue's Refresh works.
    """
    root = settings.sdlc_dir.expanduser()
    items = discover_feedback(root)
    states = _pr_states(items, refresh)
    reads = [_read(item, _state_for(states, item)) for item in items]
    return FeedbackListRead(
        root=str(root) if root.is_dir() else None,
        generated_at=utcnow(),
        counts=_counts(reads),
        items=reads,
    )


@router.post("/{feedback_id}/decision", response_model=FeedbackItemRead)
def set_feedback_decision(feedback_id: str, payload: FeedbackDecisionUpdate) -> FeedbackItemRead:
    """Record a decision (or reset to None) in one analysis file's frontmatter.

    The write stamps ``decided_at`` and leaves ``executed_at`` alone, so the item
    shows as decided but not run until ``handle-pr-reviewer-feedback`` carries it
    out. Recording the same decision again keeps an existing ``executed_at``.
    """
    root = settings.sdlc_dir.expanduser()
    path = find_feedback(root, feedback_id)
    if path is None:
        raise HTTPException(status_code=404, detail=f"feedback {feedback_id} not found")
    try:
        write_decision(path, payload.decision)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    item = parse_feedback(path)
    if item is None:
        raise HTTPException(status_code=422, detail="analysis file could not be re-read")
    state = _state_for(_pr_states([item], refresh=False), item)
    return _read(item, state)


__all__ = ["router"]
