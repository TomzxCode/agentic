"""Item stubs."""


class ItemsFake:
    def list_items(self, source=None):
        return [{"id": "i1", "source": "note", "title": "N"}]

    def get_item(self, item_id):
        return {"id": item_id, "source": "note", "title": "N"}

    def create_item(self, **fields):
        return {"id": "i2", "source": "note", "title": "N"}

    def update_item(self, item_id, **fields):
        return {"id": item_id, "source": "note", "title": "N"}

    def refresh_item(self, item_id):
        return {"id": item_id, "source": "note", "title": "N"}

    def delete_item(self, item_id):
        return None
