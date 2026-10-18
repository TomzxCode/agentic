"""CLI commands."""

from __future__ import annotations

from typing import Literal

from cyclopts import App

from .. import runtime
from ..render import (
    _join,
    _metrics_text,
)
from ..runtime import (
    ChangeClassArg,
    emit,
    safe,
)

metrics_app = App(name="metrics", help="Read autonomy rate and yield, and manage their baselines.")
baseline_app = App(name="baseline", help="Read and set the baseline each metric is compared against.")


def register(app: App) -> None:
    app.command(metrics_app)
    metrics_app.command(baseline_app)


@metrics_app.command(name="show")
@safe
def metrics_show(
    window_days: int = 30,
    observation_days: int = 14,
    tolerance: float = 0.02,
    task_id: str | None = None,
    change_class: ChangeClassArg | None = None,
) -> str:
    """Show autonomy rate and yield with their direction against the baseline."""
    with runtime._client() as client:
        report = client.get_metrics(
            window_days=window_days,
            observation_days=observation_days,
            tolerance=tolerance,
            task_id=task_id,
            change_class=change_class,
        )
    return emit(report, _metrics_text(report))


@baseline_app.command(name="list")
@safe
def baseline_list() -> str:
    """List the stored metric baselines."""
    with runtime._client() as client:
        baselines = client.list_baselines()
    return emit(baselines, _join(baselines, lambda b: f"{b['metric']}  {b['value']:.1%}  {b['captured_at'][:19]}"))


@baseline_app.command(name="set")
@safe
def baseline_set(
    metric: Literal["autonomy_rate", "yield"],
    value: float,
    window_days: int = 30,
    observation_days: int = 14,
    note: str = "",
) -> str:
    """Set a metric's baseline to the value you measured before the factory run."""
    with runtime._client() as client:
        baseline = client.set_baseline(
            metric, value, window_days=window_days, observation_days=observation_days, note=note
        )
    return emit(baseline, f"{baseline['metric']} baseline = {baseline['value']:.1%}")


@baseline_app.command(name="delete")
@safe
def baseline_delete(metric: Literal["autonomy_rate", "yield"]) -> str:
    """Clear a metric's baseline."""
    with runtime._client() as client:
        client.delete_baseline(metric)
    return emit({"deleted": metric}, f"deleted baseline {metric}")
