from pyflow.models import Workflow, WorkflowValidationError


def execution_layers(workflow: Workflow) -> list[list[str]]:
    tasks = workflow.tasks
    if not tasks:
        return []

    for task in tasks.values():
        for dep in task.dependencies:
            if dep not in tasks:
                raise WorkflowValidationError(
                    f"Zadanie '{task.name}' wymaga niezarejestrowanej zależności '{dep}'."
                )

    in_degree: dict[str, int] = {name: len(task.dependencies) for name, task in tasks.items()}
    dependents: dict[str, list[str]] = {name: [] for name in tasks}

    for name, task in tasks.items():
        for dep in task.dependencies:
            dependents[dep].append(name)

    current_layer = sorted([name for name, deg in in_degree.items() if deg == 0])
    layers: list[list[str]] = []
    visited_count = 0

    while current_layer:
        layers.append(current_layer)
        visited_count += len(current_layer)
        next_layer: list[str] = []

        for node in current_layer:
            for dependent in dependents[node]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    next_layer.append(dependent)

        current_layer = sorted(next_layer)

    if visited_count != len(tasks):
        cycle_nodes = sorted([name for name, deg in in_degree.items() if deg > 0])
        raise WorkflowValidationError(
            f"Wykryto cykl w grafie workflowu obejmujący zadania: {', '.join(cycle_nodes)}."
        )

    return layers


def topological_order(workflow: Workflow) -> list[str]:
    layers = execution_layers(workflow)
    return [task_name for layer in layers for task_name in layer]