"""Items: external things (Slack threads, GitHub issues, Drive docs, URLs, notes)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete as sa_delete
from sqlmodel import Session, col, select

from ..auto_changes import record_merged_pr_changes
from ..crud import get_or_404
from ..db import get_session
from ..models.base import utcnow
from ..models.items import Association, ItemPerson, SourceItem
from ..refresh import (
    policies_from_settings,
)
from ..reviews import list_report_files, read_report, review_dir
from ..schemas.items import (
    ItemCreate,
    ItemGithubReviewer,
    ItemGithubReviewers,
    ItemPoke,
    ItemPokeRequest,
    ItemRead,
    ItemReviewContent,
    ItemReviewFile,
    ItemReviews,
    ItemUpdate,
)
from ..schemas.settings import RefreshDueReport
from ..services.github import fetch_github_pull_reviewers
from ..services.parsing import looks_like_url, parse_github
from ..services.slack import SlackError, resolve_slack_user_id, slack_send_dm, slack_ts_after, slack_ts_datetime
from ..services.sources import fetch_source, infer_item_source
from ..settings_store import get_settings
from .items_refresh import _apply_fetch, force_refresh_source, refresh_due_items
from .people_links import link_people_to_item
from .people_service import item_person_ids, person_aliases, person_for_alias

router = APIRouter(prefix="/api/items", tags=["items"])


def _upsert_item(session: Session, payload: ItemCreate, errors: list[str] | None = None) -> SourceItem:
    # Text pasted where a URL was expected is not a URL: keep it as the note's
    # content instead of storing (and later rendering) a bogus link.
    raw_url = (payload.url or "").strip()
    url = raw_url if looks_like_url(raw_url) else None
    content = payload.content or (raw_url if raw_url and url is None else "")

    # Infer the source/kind/external id when the caller did not spell them out.
    inferred = infer_item_source(url, payload.external_id, content)
    source = payload.source or inferred["source"] or "note"
    kind = payload.kind or inferred.get("kind") or ""
    external_id = payload.external_id or inferred.get("external_id")

    item: SourceItem | None = None
    if external_id:
        item = session.exec(
            select(SourceItem).where(SourceItem.source == source, SourceItem.external_id == external_id)
        ).first()
    if item is None and url:
        item = session.exec(select(SourceItem).where(SourceItem.url == url)).first()

    if item is None:
        item = SourceItem(source=source)
        session.add(item)

    item.source = source
    item.kind = kind or item.kind
    if payload.title:
        # A title the caller supplied is the person's; a refresh will not replace it.
        item.title = payload.title
        item.title_custom = True
    if url:
        item.url = url
    item.external_id = external_id or item.external_id
    item.metadata_json = {**(item.metadata_json or {}), **payload.metadata_json}
    if content:
        item.content = content

    fetched_people: list[dict] = []
    if payload.fetch and item.url and not item.content:
        fetched = fetch_source(item.source, item.url, item.external_id, item.title)
        item.title = item.title or fetched.get("title") or item.url or item.source
        item.content = item.content or fetched.get("content", "")
        item.metadata_json = {**(item.metadata_json or {}), **fetched.get("metadata", {})}
        item.fetched_at = utcnow()
        fetched_people = fetched.get("people") or []
        if fetched.get("error") and errors is not None:
            errors.append(fetched["error"])

    if not item.title and item.content:
        item.title = item.content.strip().splitlines()[0][:120]

    item.updated_at = utcnow()
    session.add(item)
    session.commit()
    session.refresh(item)
    if fetched_people:
        # The source named people (a GitHub author/commenter, a Slack
        # participant): upsert them and link them to the item.
        link_people_to_item(session, item.id, fetched_people)
    return item


def _slack_latest_ts(item: SourceItem) -> str | None:
    """The newest Slack message timestamp a fetch stored on the item, if any."""
    latest = (item.metadata_json or {}).get("latest_ts")
    return str(latest) if latest else None


def _item_read(session: Session, item: SourceItem, fetch_error: str | None = None) -> ItemRead:
    data = ItemRead.model_validate(item)
    data.fetch_error = fetch_error
    latest_ts = _slack_latest_ts(item)
    data.done = item.done_at is not None
    data.done_at = item.done_at
    data.latest_message_at = slack_ts_datetime(latest_ts)
    # A message after the thread was marked done is flagged, but the thread
    # stays done: reopening is its own decision.
    data.new_since_done = bool(
        item.done_at is not None and latest_ts and slack_ts_after(latest_ts, item.done_message_ts)
    )
    data.task_ids = [
        assoc.task_id for assoc in session.exec(select(Association).where(Association.item_id == item.id)).all()
    ]
    data.person_ids = item_person_ids(session, item.id)
    return data


@router.get("", response_model=list[ItemRead])
def list_items(
    source: str | None = None,
    q: str | None = None,
    session: Session = Depends(get_session),
) -> list[ItemRead]:
    query = select(SourceItem).order_by(col(SourceItem.created_at).desc())
    if source:
        query = query.where(SourceItem.source == source)
    items = list(session.exec(query).all())
    if q:
        needle = q.lower()
        items = [
            item
            for item in items
            if needle in item.title.lower()
            or needle in (item.url or "").lower()
            or needle in (item.content or "").lower()
        ]
    return [_item_read(session, item) for item in items]


@router.post("", response_model=ItemRead, status_code=201)
def create_item(payload: ItemCreate, session: Session = Depends(get_session)) -> ItemRead:
    errors: list[str] = []
    item = _upsert_item(session, payload, errors=errors)
    return _item_read(session, item, fetch_error=errors[0] if errors else None)


@router.post("/refresh-due", response_model=RefreshDueReport)
def refresh_due(session: Session = Depends(get_session)) -> RefreshDueReport:
    """Re-fetch every item whose source refresh policy says it is due."""
    policies = policies_from_settings(get_settings(session))
    return RefreshDueReport.model_validate(refresh_due_items(session, policies, origin="manual"))


@router.post("/refresh-source/{source}", response_model=RefreshDueReport)
def refresh_source(source: str, session: Session = Depends(get_session)) -> RefreshDueReport:
    """Re-fetch every item of one source now, ignoring the refresh policy."""
    try:
        report = force_refresh_source(session, source)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return RefreshDueReport.model_validate(report)


@router.get("/{item_id}", response_model=ItemRead)
def get_item(item_id: str, session: Session = Depends(get_session)) -> ItemRead:
    item = get_or_404(session, SourceItem, item_id, "Item not found")
    return _item_read(session, item)


@router.patch("/{item_id}", response_model=ItemRead)
def update_item(item_id: str, payload: ItemUpdate, session: Session = Depends(get_session)) -> ItemRead:
    item = get_or_404(session, SourceItem, item_id, "Item not found")
    fields = payload.model_dump(exclude_unset=True)
    done = fields.pop("done", None)
    if done is not None:
        if done:
            # Marking done records the newest message seen; marking an already
            # done thread keeps the original moment and watermark.
            if item.done_at is None:
                item.done_at = utcnow()
                item.done_message_ts = _slack_latest_ts(item)
        else:
            item.done_at = None
            item.done_message_ts = None
    reset_title = "title" in fields and not str(fields.get("title") or "").strip()
    for key, value in fields.items():
        if value is None and key == "metadata_json":
            continue
        if key == "title" and reset_title:
            continue
        setattr(item, key, value)
        if key == "title":
            # An edited title is the person's; clearing it hands it back to the source.
            item.title_custom = bool(value)
    if reset_title:
        # Clearing the title drops the custom flag and puts the source's own
        # title back: the same name a first fetch would have produced.
        item.title_custom = False
        item.title = ""
        derived = fetch_source(item.source, item.url, item.external_id, "")
        item.title = derived.get("title") or ""
        if not item.title and item.content:
            item.title = item.content.strip().splitlines()[0][:120]
    item.updated_at = utcnow()
    session.add(item)
    session.commit()
    session.refresh(item)
    # A metadata patch can flip the PR to merged, which is a landed change.
    record_merged_pr_changes(session, item_ids=[item.id])
    return _item_read(session, item)


@router.post("/{item_id}/refresh", response_model=ItemRead)
def refresh_item(item_id: str, session: Session = Depends(get_session)) -> ItemRead:
    item = get_or_404(session, SourceItem, item_id, "Item not found")
    fetched = fetch_source(item.source, item.url, item.external_id, item.title)
    error = _apply_fetch(item, fetched, utcnow())
    session.add(item)
    session.commit()
    session.refresh(item)
    link_people_to_item(session, item.id, fetched.get("people") or [])
    # A refresh is how an already-linked PR is first seen as merged.
    record_merged_pr_changes(session, item_ids=[item.id])
    return _item_read(session, item, fetch_error=error)


def _pull_request_location(item: SourceItem) -> tuple[str, str, str] | None:
    """The (owner, repo, number) of a GitHub pull-request item, or None."""
    if item.source != "github" or not item.url:
        return None
    parsed = parse_github(item.url)
    if not parsed or parsed["kind"] != "pull_request":
        return None
    return parsed["owner"], parsed["repo"], parsed["number"]


@router.get("/{item_id}/reviews", response_model=ItemReviews)
def list_item_reviews(item_id: str, session: Session = Depends(get_session)) -> ItemReviews:
    """List the review reports the review skills wrote for a PR item.

    A non-PR item (or a PR with no report directory) returns an empty list
    rather than an error, so the UI can render the section unconditionally.
    """
    item = get_or_404(session, SourceItem, item_id, "Item not found")
    location = _pull_request_location(item)
    if location is None:
        return ItemReviews()
    directory = review_dir(*location)
    if directory is None:
        return ItemReviews()
    return ItemReviews(
        path=str(directory),
        files=[ItemReviewFile.model_validate(report) for report in list_report_files(*location)],
    )


@router.get("/{item_id}/reviewers", response_model=ItemGithubReviewers)
def list_item_github_reviewers(item_id: str, session: Session = Depends(get_session)) -> ItemGithubReviewers:
    """List the reviewers on a pull request item, read live from GitHub.

    ``ghx`` does not carry reviews, so this read goes through ``gh``. Each
    reviewer appears once, with their latest state and when they last reviewed.
    A non-PR item returns an empty list, and a read that could not run reports
    its error instead of reading as "no reviewers".
    """
    item = get_or_404(session, SourceItem, item_id, "Item not found")
    location = _pull_request_location(item)
    if location is None:
        return ItemGithubReviewers()
    reviews = fetch_github_pull_reviewers(*location)
    if reviews is None:
        return ItemGithubReviewers(
            error="Could not read this pull request's reviewers (is `gh` installed and authenticated?)"
        )
    return ItemGithubReviewers(reviewers=[ItemGithubReviewer.model_validate(review) for review in reviews])


def _slack_pr_message(item: SourceItem) -> str:
    """The message a poke sends: a wave, a robot, and the PR's title as a link."""
    url = str(item.url or "")
    title = " ".join(str(item.title or "").split())
    # Slack's link label ends at "|", and the angle brackets delimit the link.
    for char in ("|", "<", ">"):
        title = title.replace(char, "-")
    label = f"<{url}|{title}>" if title else f"<{url}>"
    return f":wave::robot_face: I would love your review on this PR: {label}"


@router.post("/{item_id}/poke", response_model=ItemPoke)
def poke_reviewer(item_id: str, payload: ItemPokeRequest, session: Session = Depends(get_session)) -> ItemPoke:
    """Send a reviewer of a pull request a Slack message asking for their review.

    The GitHub login resolves through the people directory: the person carrying
    that alias supplies the Slack user id (or handle) the message goes to. The
    DM is sent with Slack's ``chat.postMessage``, which opens it if needed.
    """
    item = get_or_404(session, SourceItem, item_id, "Item not found")
    if _pull_request_location(item) is None:
        raise HTTPException(status_code=400, detail="This item is not a GitHub pull request")
    login = (payload.login or "").strip()
    if not login:
        raise HTTPException(status_code=400, detail="Provide the reviewer's GitHub login")
    person = person_for_alias(session, login)
    if person is None:
        raise HTTPException(
            status_code=400,
            detail=(
                f"No person carries the GitHub login @{login}. Create them in People with that login "
                "and their Slack user id as aliases, then poke again."
            ),
        )
    slack_user_id = resolve_slack_user_id(person_aliases(session, person.id))
    if slack_user_id is None:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{person.name} has no Slack user id or handle among their aliases. "
                "Add one on their person page, then poke again."
            ),
        )
    try:
        sent = slack_send_dm(slack_user_id, _slack_pr_message(item))
    except SlackError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ItemPoke(
        login=login,
        slack_user_id=slack_user_id,
        name=person.name,
        ts=str(sent["ts"]) if sent.get("ts") else None,
    )


@router.get("/{item_id}/reviews/{name:path}", response_model=ItemReviewContent)
def get_item_review(item_id: str, name: str, session: Session = Depends(get_session)) -> ItemReviewContent:
    """Read one review report for a PR item, addressed by its relative path."""
    item = get_or_404(session, SourceItem, item_id, "Item not found")
    location = _pull_request_location(item)
    if location is None:
        raise HTTPException(status_code=404, detail="Item has no review reports")
    report = read_report(*location, name)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return ItemReviewContent(name=name, content=report["content"], truncated=report["truncated"])


@router.delete("/{item_id}", status_code=204)
def delete_item(item_id: str, session: Session = Depends(get_session)) -> None:
    get_or_404(session, SourceItem, item_id, "Item not found")
    session.exec(sa_delete(Association).where(col(Association.item_id) == item_id))
    session.exec(sa_delete(ItemPerson).where(col(ItemPerson.item_id) == item_id))
    session.exec(sa_delete(SourceItem).where(col(SourceItem.id) == item_id))
    session.commit()


__all__ = ["router", "_upsert_item", "force_refresh_source", "refresh_due_items"]
