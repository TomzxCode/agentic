"""Focus-stack stubs."""


class StackFake:
    def list_stack(self):
        return [
            {
                "id": "s1",
                "task_id": "t1",
                "task": {"title": "T"},
                "position": 0,
                "is_current": True,
                "execution_count": 2,
                "duration": 90,
                "created_at": "2026-01-01T00:00:00",
                "deleted_at": None,
            }
        ]

    def stack_history(self):
        return [
            {
                "id": "s0",
                "task_id": "t0",
                "task": {"title": "Old"},
                "position": 0,
                "is_current": False,
                "execution_count": 1,
                "duration": 10,
                "created_at": "2026-01-01T00:00:00",
                "deleted_at": "2026-01-02T00:00:00",
            }
        ]

    def stack_current(self):
        return {
            "id": "s1",
            "task_id": "t1",
            "task": {"title": "T"},
            "position": 0,
            "is_current": True,
            "execution_count": 2,
            "duration": 90,
        }

    def push_stack(self, **fields):
        return [
            {
                "id": "s2",
                "task_id": "t2",
                "task": {"title": fields.get("title") or "existing"},
                "position": 0,
                "is_current": True,
                "execution_count": 1,
                "duration": 0,
            }
        ]

    def pop_stack(self):
        return []

    def reorder_stack(self, entry_id, position):
        return [
            {
                "id": entry_id,
                "task_id": "t1",
                "task": {"title": "T"},
                "position": position,
                "is_current": position == 0,
                "execution_count": 1,
                "duration": 0,
            }
        ]

    def promote_stack(self, entry_id):
        return self.reorder_stack(entry_id, 0)

    def update_stack_entry(self, entry_id, **fields):
        return [
            {
                "id": entry_id,
                "task_id": "t1",
                "task": {"title": fields.get("title") or "T"},
                "position": 0,
                "is_current": True,
                "execution_count": 1,
                "duration": 0,
            }
        ]

    def remove_stack_entry(self, entry_id):
        return None
