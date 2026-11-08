from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class TaskExecutionError(Exception):
    def __init__(self, task_name: str, cause: BaseException) -> None:
        super().__init__(
            f"Zadanie '{task_name}' zakończyło się błędem {type(cause).__name__}: {cause}"
        )
        self.task_name = task_name


@dataclass(frozen=True)
class TaskState:
    name: str
    status: TaskStatus = TaskStatus.PENDING
    started_at: float | None = None
    finished_at: float | None = None
    error: TaskExecutionError | None = None
    skip_reason: str | None = None

    @property
    def duration(self) -> float | None:
        if self.started_at is None or self.finished_at is None:
            return None
        return self.finished_at - self.started_at


@dataclass(frozen=True)
class RunResult:
    outputs: Mapping[str, Any]
    task_states: Mapping[str, TaskState]
    started_at: float
    finished_at: float

    @property
    def succeeded(self) -> bool:
        return all(state.status is TaskStatus.SUCCEEDED for state in self.task_states.values())

    @property
    def duration(self) -> float:
        return self.finished_at - self.started_at

    @property
    def failed_tasks(self) -> list[str]:
        return self._names_with_status(TaskStatus.FAILED)

    @property
    def skipped_tasks(self) -> list[str]:
        return self._names_with_status(TaskStatus.SKIPPED)

    @property
    def errors(self) -> dict[str, TaskExecutionError]:
        return {
            name: state.error
            for name, state in self.task_states.items()
            if state.error is not None
        }

    def raise_for_failure(self) -> None:
        for state in self.task_states.values():
            if state.error is not None:
                raise state.error

    def _names_with_status(self, status: TaskStatus) -> list[str]:
        return [name for name, state in self.task_states.items() if state.status is status]
