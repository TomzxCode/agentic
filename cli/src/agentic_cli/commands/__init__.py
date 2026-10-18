"""CLI command modules, one per resource.

Each module builds its own cyclopts ``App`` and exposes ``register(app)``; the
root app composes them in ``agentic_cli.cli``.
"""
