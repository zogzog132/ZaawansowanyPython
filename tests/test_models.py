import pytest
from pyflow import Task, Workflow, WorkflowValidationError


def dummy_fn(inputs, params):
    return None


def test_task_valid_and_immutable():
    raw_deps = ["step_a"]
    raw_params = {"lr": 0.01}

    task = Task(
        name="train",
        function=dummy_fn,
        dependencies=raw_deps,
        params=raw_params,
        description="Trening modelu",
    )

    raw_deps.append("step_b")
    raw_params["lr"] = 0.99

    assert task.dependencies == frozenset({"step_a"})
    assert task.params["lr"] == 0.01

    with pytest.raises(TypeError):
        task.params["new_key"] = 123  # type: ignore


@pytest.mark.parametrize("invalid_name", ["", "   "])
def test_task_empty_name_raises(invalid_name):
    with pytest.raises(ValueError, match="pusta"):
        Task(name=invalid_name, function=dummy_fn)


def test_task_self_dependency_raises():
    with pytest.raises(ValueError, match="samego siebie"):
        Task(name="task_a", function=dummy_fn, dependencies=["task_a"])


def test_workflow_duplicate_task_raises():
    wf = Workflow()
    wf.add_task(Task(name="a", function=dummy_fn))
    with pytest.raises(WorkflowValidationError, match="Duplikat"):
        wf.add_task(Task(name="a", function=dummy_fn))


def test_workflow_missing_dependency_raises():
    wf = Workflow()
    wf.add_task(Task(name="b", function=dummy_fn, dependencies=["missing_a"]))
    with pytest.raises(WorkflowValidationError, match="niezarejestrowanej"):
        wf.validate()