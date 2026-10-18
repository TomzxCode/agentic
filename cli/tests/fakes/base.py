"""Base fake: context manager and health check."""


class BaseFake:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def health(self):
        return {"status": "ok", "service": "agentic"}
