"""The review queue: pull requests with review reports in the user-global store."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, col, select

from ..config import settings
from ..db import get_session
from ..models.base import utcnow
from ..models.items import Association, SourceItem
from ..review_queue import collect_review_prs, enrich_from_github
from ..reviews import read_report
from ..schemas.items import ItemReviewContent, ReviewPrRead, ReviewQueueRead, ReviewStepRead
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


@router.get("", response_model=ReviewQueueRead)
def list_review_queue(
    refresh: bool = False,
    session: Session = Depends(get_session),
) -> ReviewQueueRead:
    """Every PR with a review-report directory, with its review-step state.

    The store holds a snapshot of each PR's own fields from the review run that
    wrote its reports, so ghx supplies the live title, state, author, and
    creation time. ``refresh`` skips the short ghx result cache and re-reads
    GitHub.
    """
    items = _tracked_pull_requests(session)
    task_ids = _task_ids_for_items(session, [item.id for item in items.values()])
    rows = collect_review_prs()
    for pr in rows:
        item = items.get((pr["owner"].lower(), pr["name"].lower(), pr["number"]))
        _merge_item(pr, item, task_ids.get(item.id, []) if item else [])
    enrich_from_github(rows, refresh=refresh)

    prs: list[ReviewPrRead] = []
    for pr in rows:
        fields = {key: value for key, value in pr.items() if key not in ("store_dir", "steps")}
        prs.append(
            ReviewPrRead(
                **fields,
                steps={step: ReviewStepRead(**state) for step, state in pr["steps"].items()},
            )
        )
    counts = {
        "total": len(prs),
        # Matches the readiness light the queue shows: green means the PR could
        # be approved automatically, red means a collected signal blocks it.
        "ready": sum(1 for pr in prs if pr.readiness == "green"),
        "blocked": sum(1 for pr in prs if pr.readiness == "red"),
    }
    root = settings.sdlc_dir.expanduser()
    return ReviewQueueRead(
        root=str(root) if root.is_dir() else None,
        generated_at=utcnow(),
        counts=counts,
        prs=prs,
    )


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
