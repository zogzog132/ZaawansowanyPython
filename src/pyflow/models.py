from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

TaskFunction = Callable[[Mapping[str, Any], Mapping[str, Any]], Any]


class WorkflowValidationError(Exception):
    """Wyjątek rzucany w przypadku błędnej definicji zadania lub grafu workflowu."""


@dataclass(frozen=True)
class Task:
    name: str
    function: TaskFunction
    dependencies: frozenset[str] = field(default_factory=frozenset)
    params: Mapping[str, Any] = field(default_factory=dict)
    description: str | None = None

    def __init__(
        self,
        name: str,
        function: TaskFunction,
        dependencies: Iterable[str] | None = None,
        params: Mapping[str, Any] | None = None,
        description: str | None = None,
    ) -> None:
        if not name or not name.strip():
            raise ValueError("Nazwa zadania nie może być pusta.")

        deps_frozenset = frozenset(dependencies) if dependencies is not None else frozenset()
        if name in deps_frozenset:
            raise ValueError(f"Zadanie '{name}' nie może zależeć od samego siebie.")

        copied_params = dict(params) if params is not None else {}
        immutable_params = MappingProxyType(copied_params)

        object.__setattr__(self, "name", name)
        object.__setattr__(self, "function", function)
        object.__setattr__(self, "dependencies", deps_frozenset)
        object.__setattr__(self, "params", immutable_params)
        object.__setattr__(self, "description", description)


class Workflow:
    def __init__(self) -> None:
        self._tasks: dict[str, Task] = {}

    @property
    def tasks(self) -> Mapping[str, Task]:
        return MappingProxyType(self._tasks)

    def add_task(self, task: Task) -> None:
        if task.name in self._tasks:
            raise WorkflowValidationError(f"Duplikat zadania: '{task.name}' już istnieje w workflow.")
        self._tasks[task.name] = task

    def validate(self) -> None:
        for task in self._tasks.values():
            for dep in task.dependencies:
                if dep not in self._tasks:
                    raise WorkflowValidationError(
                        f"Zadanie '{task.name}' wymaga niezarejestrowanej zależności '{dep}'."
                    )

        from pyflow.graph import execution_layers
        execution_layers(self)