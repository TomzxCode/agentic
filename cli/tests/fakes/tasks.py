"""Task, deadline, dependency, and association stubs."""


class TasksFake:
    def list_tasks(self, status=None, q=None, tags=None):
        return [{"id": "t1", "status": "open", "priority": 1, "title": "T", "tags": ["bug"]}]

    def list_deadlines(self, within_days=7):
        return [
            {
                "id": "t1",
                "status": "open",
                "priority": 1,
                "title": "T",
                "tags": [],
                "deadline": "2026-01-02T00:00:00",
            }
        ]

    def get_task(self, task_id):
        return {
            "id": task_id,
            "status": "open",
            "priority": 1,
            "title": "T",
            "summary": "s",
            "next_steps": [{"text": "a", "done": False}],
            "requesters": [{"id": "p1", "name": "Ada"}],
        }

    def create_task(self, **fields):
        return {"id": "t2", "title": fields.get("title")}

    def update_task(self, task_id, **fields):
        return {"id": task_id, "status": "open", "priority": 1, "title": "T"}

    def set_task_deadline(self, task_id, deadline):
        return {"id": task_id, "status": "open", "priority": 1, "title": "T", "deadline": deadline}

    def delete_task(self, task_id):
        return None

    def task_timeline(self, task_id):
        return [{"created_at": "2026-01-01T00:00:00", "type": "created", "message": "m"}]

    def task_dependencies(self, task_id):
        return {
            "task_id": task_id,
            "before": [{"id": "t0", "status": "done", "priority": 1, "title": "First"}],
            "after": [],
        }

    def add_dependency(self, task_id, related_id, relation="after"):
        return {
            "task_id": task_id,
            "before": [],
            "after": [{"id": related_id, "status": "open", "priority": 1, "title": "Next"}],
        }

    def remove_dependency(self, task_id, related_id):
        return None

    def get_graph(self, include_done=False):
        return {"nodes": [{"id": "t1"}, {"id": "t2"}], "edges": [{"before_id": "t1", "after_id": "t2"}]}

    def associate(self, task_id, **kwargs):
        return {"item": {"id": "i1"}}

    def unassociate(self, task_id, item_id):
        return None
