"""Pydantic request/response models."""

from __future__ import annotations

from pydantic import BaseModel


class GithubIssue(BaseModel):
    number: int
    title: str = ""
    url: str = ""
    state: str = ""
    author: str | None = None
    labels: list[str] = []
    body: str = ""


class GithubIssueCreate(BaseModel):
    """The title/body for a new issue, in a registered repository or an explicit one."""

    repository_id: str | None = None
    owner: str | None = None
    repo: str | None = None
    title: str
    body: str = ""


class GithubRepoItem(BaseModel):
    """An issue or pull request of a repository, as listed for browsing.

    Unlike :class:`GithubIssue` (which backs issue import), this carries the
    kind and the pull-request-only fields a repository view needs to render the
    row: whether it is a draft and, once merged, when.
    """

    number: int
    kind: str = "issue"
    title: str = ""
    url: str = ""
    state: str = ""
    is_draft: bool = False
    merged_at: str | None = None
    created_at: str | None = None
    author: str | None = None
    labels: list[str] = []


class GithubRepoListing(BaseModel):
    """A repository's issues and pull requests, plus each kind ghx could not list."""

    items: list[GithubRepoItem] = []
    failed: list[str] = []
