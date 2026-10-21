"""The review queue: pull requests with review reports in the user-global store."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, col, select

from ..config import settings
from ..crud import get_task_or_404
from ..db import get_session
from ..models.base import utcnow
from ..models.items import Association, SourceItem
from ..review_findings import DECISIONS, collect_findings, record_decisions
from ..review_queue import collect_review_prs, enrich_from_github
from ..review_scan import ReviewRequest, review_scan_state, run_review_scan, stored_review_requests
from ..reviews import read_report
from ..schemas.items import (
    ItemReviewContent,
    ReviewFindingRead,
    ReviewFindingsDecisions,
    ReviewPrRead,
    ReviewQueueRead,
    ReviewScanRead,
    ReviewStepRead,
)
from ..services.parsing import parse_github

router = APIRouter(prefix="/api/reviews", tags=["reviews"])


def _tracked_pull_requests(session: Session) -> dict[tuple[str, str, int], SourceItem]:
    """The app's tracked GitHub pull-request items, keyed by (owner, repo, number).

    A PR the app already tracks carries GitHub fields the store does not (its
    draft flag, its live state, a person-set title), so an item enriches the
    matching store row. Keys are lowercased: GitHub owner/repo casing can differ
    from the store's directory names.
    """
    items: dict[tuple[str, str, int], SourceItem] = {}
    for item in session.exec(select(SourceItem).where(SourceItem.source == "github")).all():
        parsed = parse_github(item.url or "")
        if not parsed or parsed["kind"] != "pull_request":
            continue
        key = (parsed["owner"].lower(), parsed["repo"].lower(), int(parsed["number"]))
        items[key] = item
    return items


def _task_ids_for_items(session: Session, item_ids: list[str]) -> dict[str, list[str]]:
    """The tasks each tracked item is associated to, keyed by item id.

    An item links to tasks through an ``Association``; the queue shows the link
    so a PR that already has a task is not offered an import it does not need.
    """
    if not item_ids:
        return {}
    by_item: dict[str, list[str]] = {}
    rows = session.exec(select(Association).where(col(Association.item_id).in_(item_ids))).all()
    for assoc in rows:
        by_item.setdefault(assoc.item_id, []).append(assoc.task_id)
    return by_item


def _merge_item(pr: dict, item: SourceItem | None, task_ids: list[str]) -> dict:
    """Fill a store row from its tracked item, when one exists.

    The item wins where it has a value: the app refreshes it, so its state and
    draft flag are newer than the store's review-time snapshot. The tasks the
    item is associated to ride along, so the queue can link them.
    """
    if item is None:
        return pr
    metadata = item.metadata_json or {}
    pr["item_id"] = item.id
    pr["task_ids"] = task_ids
    if item.title:
        pr["title"] = item.title
    if item.url:
        pr["url"] = item.url
    if metadata.get("author"):
        pr["author"] = metadata["author"]
    if metadata.get("state"):
        pr["state"] = metadata["state"]
    pr["draft"] = bool(metadata.get("is_draft", pr.get("draft", False)))
    return pr


def _key(pr: dict) -> tuple[str, str, int]:
    """A store row's identity, lowercased the way GitHub casing can differ."""
    return (str(pr["owner"]).lower(), str(pr["name"]).lower(), int(pr["number"]))


def _scan_row(recorded: ReviewRequest) -> dict:
    """A pull request the review scan found, as a queue row.

    It has no report yet, so every step is empty and the readiness light is
    yellow: nothing clears it for approval, and nothing blocks it either.
    """
    owner, _, name = recorded.repository.partition("/")
    return {
        "owner": owner,
        "name": name or recorded.repository,
        "repository": recorded.repository,
        "number": recorded.number,
        "title": recorded.title,
        "url": recorded.url,
        "author": recorded.author,
        "state": recorded.state,
        "draft": recorded.draft,
        "created_at": recorded.created_at,
        "labels": [],
        "review_decision": "",
        "head_commit": "",
        "steps": {},
        "in_progress": {},
        "stale_steps": [],
        "reviewed_steps": 0,
        "readiness": "yellow",
        "status": "unreviewed",
        "request_source": recorded.source,
    }


def _collect_enriched_rows(
    session: Session,
    keys: set[tuple[str, str, int]] | None = None,
    refresh: bool = False,
) -> list[dict]:
    """The store's PR rows, merged with the app's tracked items and ghx fields.

    With *keys*, only the rows in that set are read and enriched, so a
    task-scoped read does not shell out for every PR in the store.

    The review scan's finds are appended: pull requests GitHub says are awaiting
    a review, which usually have no report at all yet. They carry their own
    GitHub fields from the search, so they take the item merge but no second ghx
    lookup.
    """
    items = _tracked_pull_requests(session)
    task_ids = _task_ids_for_items(session, [item.id for item in items.values()])
    rows = collect_review_prs()
    if keys is not None:
        rows = [pr for pr in rows if _key(pr) in keys]
    for pr in rows:
        item = items.get(_key(pr))
        _merge_item(pr, item, task_ids.get(item.id, []) if item else [])
    enrich_from_github(rows, refresh=refresh)

    # The scan's finds ride along: a PR it reports is awaiting a review whether
    # or not a report already exists for it, so a store row takes the source too.
    scanned = {_key(_scan_row(recorded)): recorded for recorded in stored_review_requests(session)}
    seen = set()
    for pr in rows:
        key = _key(pr)
        seen.add(key)
        recorded = scanned.get(key)
        if recorded is not None:
            pr["request_source"] = recorded.source
    for key, recorded in scanned.items():
        if key in seen or (keys is not None and key not in keys):
            continue
        row = _scan_row(recorded)
        item = items.get(key)
        _merge_item(row, item, task_ids.get(item.id, []) if item else [])
        rows.append(row)
    rows.sort(key=lambda pr: (str(pr["repository"]).lower(), -int(pr["number"])))
    return rows


def _rows_to_read(rows: list[dict]) -> list[ReviewPrRead]:
    return [
        ReviewPrRead(
            **{key: value for key, value in pr.items() if key not in ("store_dir", "steps")},
            steps={step: ReviewStepRead(**state) for step, state in pr["steps"].items()},
        )
        for pr in rows
    ]


def _queue_response(prs: list[ReviewPrRead]) -> ReviewQueueRead:
    root = settings.sdlc_dir.expanduser()
    return ReviewQueueRead(
        root=str(root) if root.is_dir() else None,
        generated_at=utcnow(),
        counts={
            "total": len(prs),
            # Matches the readiness light the queue shows: green means the PR
            # could be approved automatically, red means a signal blocks it.
            "ready": sum(1 for pr in prs if pr.readiness == "green"),
            "blocked": sum(1 for pr in prs if pr.readiness == "red"),
        },
        prs=prs,
    )


def _task_pull_requests(session: Session, task_id: str) -> set[tuple[str, str, int]]:
    """The (owner, repo, number) of the pull requests a task's items link to."""
    keys: set[tuple[str, str, int]] = set()
    items = session.exec(
        select(SourceItem)
        .join(Association, col(Association.item_id) == col(SourceItem.id))
        .where(col(Association.task_id) == task_id)
    ).all()
    for item in items:
        if item.source != "github" or not item.url:
            continue
        parsed = parse_github(item.url)
        if parsed and parsed["kind"] == "pull_request":
            keys.add((parsed["owner"].lower(), parsed["repo"].lower(), int(parsed["number"])))
    return keys


@router.get("", response_model=ReviewQueueRead)
def list_review_queue(
    refresh: bool = False,
    session: Session = Depends(get_session),
) -> ReviewQueueRead:
    """Every PR with a review-report directory, plus the ones awaiting a review.

    The store holds a snapshot of each PR's own fields from the review run that
    wrote its reports, so ghx supplies the live title, state, author, and
    creation time. ``refresh`` skips the short ghx result cache and re-reads
    GitHub. The pull requests the review scan found (see ``GET /api/reviews/scan``)
    are included even when no report exists for them yet.
    """
    return _queue_response(_rows_to_read(_collect_enriched_rows(session, refresh=refresh)))


@router.get("/scan", response_model=ReviewScanRead)
def read_review_scan(session: Session = Depends(get_session)) -> ReviewScanRead:
    """The review scan's cadence, its last pass, and how many PRs it holds."""
    return ReviewScanRead.model_validate(review_scan_state(session))


@router.post("/scan", response_model=ReviewScanRead)
def scan_review_requests(session: Session = Depends(get_session)) -> ReviewScanRead:
    """Run the review scan now, ignoring its cadence.

    A scan that cannot run (``gh`` missing or unauthenticated) records the error
    and leaves the stored set as it was, so the queue is never emptied by a
    failure; the response carries that error.
    """
    run_review_scan(session, origin="manual", force=True)
    return ReviewScanRead.model_validate(review_scan_state(session))


@router.get("/task/{task_id}", response_model=ReviewQueueRead)
def task_review_queue(
    task_id: str,
    refresh: bool = False,
    session: Session = Depends(get_session),
) -> ReviewQueueRead:
    """The review-queue rows for the pull requests a task is linked to.

    A task links a pull request through its GitHub items; only the matching
    store rows are read and enriched. A task with no linked pull request, or
    whose PRs have no review reports, returns an empty queue.
    """
    get_task_or_404(session, task_id)
    keys = _task_pull_requests(session, task_id)
    rows = _collect_enriched_rows(session, keys=keys, refresh=refresh) if keys else []
    return _queue_response(_rows_to_read(rows))


@router.get("/findings/{number}", response_model=list[ReviewFindingRead])
def list_review_findings(number: int, repository: str) -> list[ReviewFindingRead]:
    """The must/should/may findings a PR's review skills recorded.

    Findings are read from each skill's state file (``review.yaml``,
    ``validate.yaml``, ``verify.yaml``) under the PR's review directory, so the
    app can offer them for the reviewer to forward to the author. A PR with no
    review directory returns an empty list rather than an error. ``repository``
    is ``owner/name``, or the name alone for a store keyed without an owner.
    """
    owner, _, repo = repository.partition("/")
    if not repo:
        owner, repo = "", owner
    return [ReviewFindingRead(**finding) for finding in collect_findings(owner, repo, number)]


@router.post("/findings/{number}/decisions", response_model=list[ReviewFindingRead])
def record_review_finding_decisions(number: int, payload: ReviewFindingsDecisions) -> list[ReviewFindingRead]:
    """Record the reviewer's include/skip decisions on a PR's findings.

    The decision is written onto the finding's entry in its skill's state file,
    beside the skill's own status, so the choice outlives the page and the review
    skills can read it. The updated findings are returned, which is what the
    share list re-renders. A decision for a finding the store does not hold (the
    skill rewrote its state in the meantime) is a 404 and writes nothing.
    """
    owner, _, repo = payload.repository.partition("/")
    if not repo:
        owner, repo = "", owner
    for decision in payload.decisions:
        if decision.decision not in DECISIONS:
            raise HTTPException(status_code=400, detail=f"decision must be one of {', '.join(DECISIONS)}")
    missing = record_decisions(owner, repo, number, [decision.model_dump() for decision in payload.decisions])
    if missing:
        titles = ", ".join(f"{item['step']}: {item['title']}" for item in missing)
        raise HTTPException(status_code=404, detail=f"Finding not found: {titles}")
    return [ReviewFindingRead(**finding) for finding in collect_findings(owner, repo, number)]


@router.get("/report/{number}/{name:path}", response_model=ItemReviewContent)
def get_review_report(
    number: int,
    name: str,
    repository: str,
) -> ItemReviewContent:
    """Read one PR's review report, addressed by repository and relative path.

    The queue's rows carry the report names; this serves their Markdown without
    needing the PR tracked as an item (``GET /api/items/{id}/reviews/{name}``
    covers a PR that is tracked). ``repository`` is ``owner/name``, or the name
    alone for a store keyed without an owner.
    """
    owner, _, repo = repository.partition("/")
    if not repo:
        owner, repo = "", owner
    report = read_report(owner, repo, number, name)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return ItemReviewContent(name=name, content=report["content"], truncated=report["truncated"])


__all__ = ["router"]
