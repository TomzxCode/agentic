"""Person and requester link stubs."""


class PeopleFake:
    def list_people(self):
        return [{"id": "p1", "name": "Ada", "task_count": 1, "item_count": 0}]

    def get_person(self, person_id):
        return {
            "id": person_id,
            "name": "Ada",
            "task_count": 1,
            "item_count": 1,
            "aliases": ["ada", "ada@example.com"],
            "notes": "n",
            "task_ids": ["t1"],
            "item_ids": ["i1"],
        }

    def create_person(self, **fields):
        return {"id": "p2", "name": fields.get("name"), "task_count": 0, "item_count": 0}

    def update_person(self, person_id, **fields):
        return {"id": person_id, "name": fields.get("name") or "Ada", "task_count": 0, "item_count": 0}

    def delete_person(self, person_id):
        return None

    def link_person(self, person_id, **kwargs):
        return {"id": person_id, "name": "Ada", "task_count": 1, "item_count": 0}

    def unlink_person(self, person_id, **kwargs):
        return None

    def link_requester(self, person_id, task_id):
        return {"id": person_id, "name": "Ada", "task_count": 1, "item_count": 0}

    def unlink_requester(self, person_id, task_id):
        return None

    def merge_person(self, source_id, target_id):
        return {"id": target_id, "name": "Grace", "task_count": 1, "item_count": 0}
