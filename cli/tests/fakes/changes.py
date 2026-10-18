"""Change, metrics, and baseline stubs."""


class ChangesFake:
    def list_changes(self, task_id=None, status=None, change_class=None):
        return [{"id": "c1", "status": "proposed", "change_class": "feature", "title": "C", "human_intervened": False}]

    def get_change(self, change_id):
        return {
            "id": change_id,
            "status": "accepted",
            "change_class": "bugfix",
            "title": "C",
            "human_intervened": True,
            "external_ref": "https://example/pr/1",
            "opened_at": "2026-01-01T00:00:00",
            "accepted_at": "2026-01-02T00:00:00",
            "interventions": [{"kind": "correction", "note": "n"}],
        }

    def create_change(self, **fields):
        return {
            "id": "c2",
            "status": "proposed",
            "change_class": fields.get("change_class"),
            "title": fields.get("title"),
        }

    def transition_change(self, change_id, status):
        return {"id": change_id, "status": status, "change_class": "feature", "title": "C"}

    def add_intervention(self, change_id, kind="other", note=""):
        return {"id": "i1", "kind": kind, "note": note}

    def delete_change(self, change_id):
        return None

    def get_metrics(self, **kwargs):
        return {
            "window_days": 30,
            "observation_days": 14,
            "tolerance": 0.02,
            "metrics": [
                {
                    "label": "Autonomy rate",
                    "value": 0.5,
                    "baseline": 0.2,
                    "delta": 0.3,
                    "direction": "improving",
                    "numerator": 1,
                    "denominator": 2,
                }
            ],
            "counts": {
                "accepted": 2,
                "touchless": 1,
                "reverted": 0,
                "rejected": 0,
                "pending_observation": 0,
                "open": 0,
            },
        }

    def list_baselines(self):
        return [{"metric": "autonomy_rate", "value": 0.2, "captured_at": "2026-01-01T00:00:00"}]

    def set_baseline(self, metric, value, **fields):
        return {"metric": metric, "value": value}

    def delete_baseline(self, metric):
        return None
