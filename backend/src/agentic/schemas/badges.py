"""Pydantic request/response models."""

from __future__ import annotations

from pydantic import BaseModel


class NavBadgesRead(BaseModel):
    """The counts the sidebar nav badges show.

    Each field matches one nav item id on the client (``reviews``, ``my-pulls``,
    ``feedback``); a page with nothing waiting reports zero and shows no badge.
    """

    reviews: int = 0
    my_pulls: int = 0
    feedback: int = 0
