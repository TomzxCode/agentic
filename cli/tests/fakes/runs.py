"""Run, session, context, and run-stream stubs."""


class RunsFake:
    def list_runs(self, task_id):
        return [{"id": "r1", "status": "queued", "kind": "chat", "prompt": "p"}]

    def get_run(self, run_id):
        return {
            "id": run_id,
            "status": "succeeded",
            "kind": "chat",
            "prompt": "p",
            "session_id": "s",
            "cwd": "/w",
            "links": [{"label": "L", "url": "u"}],
        }

    def run_events(self, run_id):
        return [{"type": "message", "text": "hi"}]

    def create_run(self, task_id, prompt, **kwargs):
        return {"id": "r3", "status": "queued", "cwd": "/w"}

    def cancel_run(self, run_id):
        return {"id": run_id, "status": "cancelled"}

    def list_sessions(self, task_id):
        return [{"id": "s1", "task_id": task_id, "session_id": "ses_1", "label": "first"}]

    def get_session(self, task_id, session_id):
        return {
            "id": session_id,
            "task_id": task_id,
            "session_id": "ses_1",
            "label": "first",
            "harness_id": "opencode",
            "cwd": "/w",
            "links": [{"label": "L", "command": "c"}],
        }

    def create_session(self, task_id, session_id, harness_id=None, cwd=None, label=""):
        return {"id": "s2", "task_id": task_id, "session_id": session_id, "label": label}

    def update_session(self, task_id, session_id, **fields):
        return {"id": session_id, "task_id": task_id, "session_id": "ses_1", "label": fields.get("label") or "first"}

    def delete_session(self, task_id, session_id):
        return None

    def get_context(self, task_id):
        return {"summary": "s", "next_steps": [{"text": "a", "done": True}]}

    def refresh_context(self, task_id):
        return {"id": "r4"}

    def stream_run(self, run_id):
        return iter([{"type": "message", "text": "hi"}, {"type": "run_finished", "text": ""}])
