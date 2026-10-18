from pathlib import Path

from fastapi.testclient import TestClient

from agentic.main import app
from agentic.services.prompts import build_context_prompt


def _repo(client: TestClient, path: Path) -> dict:
    path.mkdir(parents=True, exist_ok=True)
    (path / ".git").mkdir(exist_ok=True)
    return client.post("/api/repositories", json={"path": str(path)}).json()


def test_group_lifecycle_and_task_link(tmp_path: Path):
    with TestClient(app) as client:
        a = _repo(client, tmp_path / "alpha")
        b = _repo(client, tmp_path / "beta")

        created = client.post(
            "/api/groups",
            json={"name": "Core", "description": "core repos", "repository_ids": [a["id"], b["id"]]},
        )
        assert created.status_code == 201
        group = created.json()
        assert sorted(group["repository_ids"]) == sorted([a["id"], b["id"]])

        # unknown repository ids are ignored
        updated = client.patch(f"/api/groups/{group['id']}", json={"repository_ids": [a["id"], "nope"]}).json()
        assert updated["repository_ids"] == [a["id"]]

        task = client.post("/api/tasks", json={"title": "Grouped", "group_id": group["id"]}).json()
        assert task["group_id"] == group["id"]

        # deleting the group detaches it from the task
        assert client.delete(f"/api/groups/{group['id']}").status_code == 204
        assert client.get(f"/api/tasks/{task['id']}").json()["group_id"] is None

        client.delete(f"/api/tasks/{task['id']}")
        client.delete(f"/api/repositories/{a['id']}")
        client.delete(f"/api/repositories/{b['id']}")


def test_context_prompt_includes_group():
    prompt = build_context_prompt(
        {
            "title": "T",
            "description": "",
            "status": "open",
            "priority": 1,
            "repository": None,
            "group": {"name": "Core", "description": "core repos", "repositories": ["/repos/alpha", "/repos/beta"]},
            "worktrees": [],
        },
        [],
    )
    assert "## Repository group: Core" in prompt
    assert "/repos/alpha" in prompt
    assert "/repos/beta" in prompt
