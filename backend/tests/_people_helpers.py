"""Shared helpers for the split people API tests."""

from fastapi.testclient import TestClient


def _task(client: TestClient, title: str = "Task") -> str:
    return client.post("/api/tasks", json={"title": title}).json()["id"]


def _item(client: TestClient, title: str = "Item") -> str:
    return client.post("/api/items", json={"title": title, "content": "x", "fetch": False}).json()["id"]


def _person(client: TestClient, name: str = "Ada Lovelace") -> str:
    return client.post("/api/people", json={"name": name}).json()["id"]


def _stub_fetch(monkeypatch, people):
    from agentic.routers import items as items_router

    monkeypatch.setattr(
        items_router,
        "fetch_source",
        lambda *args, **kwargs: {"metadata": {}, "content": "body", "title": "T", "people": people},
    )
