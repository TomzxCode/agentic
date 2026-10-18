"""Shared CRUD helpers."""

import pytest
from fastapi import HTTPException
from sqlmodel import Session

from agentic.crud import field_label, get_task_or_404, jsonable
from agentic.db import create_db_and_tables, engine
from agentic.models.base import TaskStatus


def test_jsonable_and_field_label():
    assert jsonable(TaskStatus.in_progress) == "in_progress"
    assert jsonable(7) == 7
    assert field_label("group_id") == "group"
    assert field_label("harness_id") == "harness"
    assert field_label("next_steps") == "next steps"


def test_get_task_or_404_raises_for_a_missing_task():
    create_db_and_tables()
    with Session(engine) as session, pytest.raises(HTTPException) as excinfo:
        get_task_or_404(session, "does-not-exist")
    assert excinfo.value.status_code == 404
