"""Tag, repository, harness, worktree, settings, and operation stubs."""


class MiscFake:
    def list_tags(self):
        return [{"name": "bug", "count": 1}]

    def list_repositories(self):
        return [{"id": "r1", "name": "r", "path": "/p"}]

    def add_repository(self, path, name=None):
        return {"id": "r2", "name": "r", "path": path}

    def remove_repository(self, repository_id):
        return None

    def list_harnesses(self, full=False):
        return [{"id": "opencode", "available": True, "detail": "/usr/bin/opencode"}]

    def create_harness(self, **fields):
        return {"id": "h1", "command": fields.get("command")}

    def update_harness(self, harness_id, **fields):
        return {"id": harness_id, "command": "c"}

    def delete_harness(self, harness_id):
        return None

    def list_worktrees(self, task_id):
        return [{"id": "w1", "status": "active", "branch": "b", "path": "/w"}]

    def create_worktree(self, task_id, repository_id=None, branch=None, base=None):
        return {"id": "w2", "branch": "b", "path": "/w"}

    def remove_worktree(self, task_id, worktree_id):
        return None

    def get_settings(self):
        return {"effective": {"openchamber_url": "x"}}

    def update_settings(self, **fields):
        return {"effective": {"openchamber_url": "x"}}

    def list_operations(self, client=None, actor=None, limit=100):
        return [
            {
                "id": "o1",
                "method": "POST",
                "path": "/api/tasks",
                "status_code": 201,
                "client": "cli",
                "actor": "agent",
                "created_at": "2026-01-01T00:00:00",
            }
        ]
