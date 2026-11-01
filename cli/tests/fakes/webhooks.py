"""Webhook / event bus stubs."""

ENDPOINT = {
    "id": "e1",
    "name": "GitHub",
    "description": "Pull requests",
    "kind": "github",
    "secret": "s3cret",
    "enabled": True,
    "subscription_count": 1,
    "event_count": 2,
    "created_at": "2026-01-02T09:00:00",
    "updated_at": "2026-01-02T09:00:00",
}


def subscription():
    return {
        "id": "s1",
        "endpoint_id": "e1",
        "graph_id": "g1",
        "graph_name": "On PR",
        "name": "PR opened",
        "events": ["pull_request"],
        "filters": [{"path": "action", "equals": "opened"}],
        "enabled": True,
        "created_at": "2026-01-02T09:00:00",
        "updated_at": "2026-01-02T09:00:00",
    }


def event():
    return {
        "id": "ev1",
        "endpoint_id": "e1",
        "endpoint_name": "GitHub",
        "source": "github",
        "event_type": "pull_request",
        "delivery_id": "abc",
        "payload": {"action": "opened"},
        "headers": {},
        "delivery_count": 1,
        "created_at": "2026-01-02T09:00:00",
    }


class WebhooksFake:
    def list_webhook_endpoints(self):
        return [dict(ENDPOINT)]

    def get_webhook_endpoint(self, endpoint_id):
        return dict(ENDPOINT)

    def create_webhook_endpoint(self, name, *, description=None, kind=None, secret=None, enabled=None):
        return {**ENDPOINT, "name": name, "kind": kind or "generic", "secret": secret or ""}

    def update_webhook_endpoint(self, endpoint_id, **fields):
        fields = {key: value for key, value in fields.items() if value is not None}
        return {**ENDPOINT, **fields}

    def delete_webhook_endpoint(self, endpoint_id):
        return None

    def list_webhook_subscriptions(self, endpoint_id=None):
        return [subscription()]

    def create_webhook_subscription(self, endpoint_id, graph_id, *, name=None, events=None, filters=None, enabled=None):
        return {
            **subscription(),
            "endpoint_id": endpoint_id,
            "graph_id": graph_id,
            "name": name or "",
            "events": events or [],
            "filters": filters or [],
            "enabled": True if enabled is None else enabled,
        }

    def update_webhook_subscription(self, subscription_id, **fields):
        fields = {key: value for key, value in fields.items() if value is not None}
        return {**subscription(), **fields}

    def delete_webhook_subscription(self, subscription_id):
        return None

    def list_webhook_events(self, endpoint_id=None, event_type=None, limit=50):
        return [event()]

    def get_webhook_event(self, event_id):
        return {
            **event(),
            "deliveries": [
                {
                    "id": "d1",
                    "event_id": event_id,
                    "subscription_id": "s1",
                    "subscription_name": "PR opened",
                    "graph_id": "g1",
                    "graph_name": "On PR",
                    "graph_execution_id": "x1",
                    "status": "started",
                    "error": "",
                    "created_at": "2026-01-02T09:00:00",
                }
            ],
        }

    def replay_webhook_event(self, event_id):
        return {
            "id": event_id,
            "event_type": "pull_request",
            "deliveries": self.get_webhook_event(event_id)["deliveries"],
        }

    def test_webhook_endpoint(self, endpoint_id, *, event_type="test", payload=None):
        return {"id": "ev2", "event_type": event_type, "deliveries": []}
