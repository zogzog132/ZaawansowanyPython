import time
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from pyflow.graph import topological_order
from pyflow.models import Task, Workflow
from pyflow.results import RunResult, TaskExecutionError, TaskState, TaskStatus


def run(workflow: Workflow) -> RunResult:
    run_started = time.perf_counter()

    workflow.validate()
    plan = topological_order(workflow)

    states: dict[str, TaskState] = {name: TaskState(name=name) for name in plan}
    outputs: dict[str, Any] = {}

    for name in plan:
        task = workflow.tasks[name]

        blocked_by = sorted(
            dep for dep in task.dependencies if states[dep].status is not TaskStatus.SUCCEEDED
        )
        if blocked_by:
            states[name] = TaskState(
                name=name,
                status=TaskStatus.SKIPPED,
                skip_reason=_skip_reason(blocked_by, states),
            )
            continue

        inputs = MappingProxyType({dep: outputs[dep] for dep in sorted(task.dependencies)})

        started = time.perf_counter()
        states[name] = TaskState(name=name, status=TaskStatus.RUNNING, started_at=started)
        try:
            output = _call_task(task, inputs)
        except TaskExecutionError as error:
            states[name] = TaskState(
                name=name,
                status=TaskStatus.FAILED,
                started_at=started,
                finished_at=time.perf_counter(),
                error=error,
            )
        else:
            finished = time.perf_counter()
            outputs[name] = output
            states[name] = TaskState(
                name=name,
                status=TaskStatus.SUCCEEDED,
                started_at=started,
                finished_at=finished,
            )

    return RunResult(
        outputs=MappingProxyType(outputs),
        task_states=MappingProxyType(states),
        started_at=run_started,
        finished_at=time.perf_counter(),
    )


def _call_task(task: Task, inputs: Mapping[str, Any]) -> Any:
    try:
        return task.function(inputs, task.params)
    except Exception as exc:
        raise TaskExecutionError(task.name, exc) from exc


def _skip_reason(blocked_by: list[str], states: Mapping[str, TaskState]) -> str:
    details = ", ".join(f"{dep} ({states[dep].status.value})" for dep in blocked_by)
    return f"zależności nie zakończyły się sukcesem: {details}"
