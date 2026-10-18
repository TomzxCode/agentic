"""Scheduled-task stubs."""


class SchedulesFake:
    def list_schedules(self):
        return [
            {
                "id": "s1",
                "name": "N",
                "command": "echo hi",
                "schedule": "0 9 * * *",
                "cwd": None,
                "timezone": "Europe/Paris",
                "enabled": True,
                "next_run_at": "2026-01-02T09:00:00Z",
                "last_status": "succeeded",
            }
        ]

    def get_schedule(self, schedule_id):
        return self.list_schedules()[0]

    def create_schedule(self, name, command, schedule, cwd=None, timezone=None, enabled=None):
        return {
            **self.list_schedules()[0],
            "id": "s2",
            "name": name,
            "command": command,
            "schedule": schedule,
            "timezone": timezone or self.list_schedules()[0]["timezone"],
        }

    def update_schedule(self, schedule_id, **fields):
        # Mirror the real client, which drops None so the API keeps its defaults.
        fields = {key: value for key, value in fields.items() if value is not None}
        return {**self.list_schedules()[0], **fields}

    def delete_schedule(self, schedule_id):
        return None

    def run_schedule(self, schedule_id):
        return {"id": "r1", "scheduled_task_id": schedule_id, "status": "running"}

    def schedule_runs(self, schedule_id, limit=20):
        return [
            {
                "id": "r1",
                "scheduled_task_id": schedule_id,
                "status": "succeeded",
                "exit_code": 0,
                "output": "hi\n",
                "started_at": "2026-01-02T09:00:00",
            }
        ]

    def schedule_executions(self, limit=100):
        run = self.schedule_runs("s1")[0]
        return [{**run, "task_name": "Nightly", "task_command": "echo hi"}]
