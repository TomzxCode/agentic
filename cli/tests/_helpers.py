"""Shared test doubles for the CLI command tests."""

from fakes.base import BaseFake
from fakes.changes import ChangesFake
from fakes.items import ItemsFake
from fakes.misc import MiscFake
from fakes.people import PeopleFake
from fakes.runs import RunsFake
from fakes.schedules import SchedulesFake
from fakes.stack import StackFake
from fakes.tasks import TasksFake
from fakes.webhooks import WebhooksFake


class FakeClient(
    BaseFake,
    TasksFake,
    PeopleFake,
    ItemsFake,
    ChangesFake,
    RunsFake,
    StackFake,
    SchedulesFake,
    MiscFake,
    WebhooksFake,
):
    """A stand-in for AgenticClient returning plausible shapes per method."""
