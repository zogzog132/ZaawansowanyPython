import pytest
from pyflow import Task, Workflow, WorkflowValidationError, execution_layers, topological_order


def dummy_fn(inputs, params):
    return None


def test_empty_graph():
    wf = Workflow()
    assert topological_order(wf) == []
    assert execution_layers(wf) == []


def test_single_node():
    wf = Workflow()
    wf.add_task(Task(name="only_one", function=dummy_fn))
    assert topological_order(wf) == ["only_one"]
    assert execution_layers(wf) == [["only_one"]]


def test_chain_graph():
    wf = Workflow()
    wf.add_task(Task(name="c", function=dummy_fn, dependencies=["b"]))
    wf.add_task(Task(name="b", function=dummy_fn, dependencies=["a"]))
    wf.add_task(Task(name="a", function=dummy_fn))

    assert topological_order(wf) == ["a", "b", "c"]
    assert execution_layers(wf) == [["a"], ["b"], ["c"]]


def test_independent_tasks_and_determinism():
    wf1 = Workflow()
    for name in ["z", "a", "m"]:
        wf1.add_task(Task(name=name, function=dummy_fn))

    wf2 = Workflow()
    for name in ["m", "z", "a"]:
        wf2.add_task(Task(name=name, function=dummy_fn))

    assert topological_order(wf1) == ["a", "m", "z"]
    assert topological_order(wf2) == ["a", "m", "z"]
    assert execution_layers(wf1) == [["a", "m", "z"]]


def test_execution_layers_diamond_example():
    wf = Workflow()
    wf.add_task(Task(name="extract", function=dummy_fn))
    wf.add_task(Task(name="clean_b", function=dummy_fn, dependencies=["extract"]))
    wf.add_task(Task(name="clean_a", function=dummy_fn, dependencies=["extract"]))
    wf.add_task(Task(name="report", function=dummy_fn, dependencies=["clean_a", "clean_b"]))

    assert execution_layers(wf) == [["extract"], ["clean_a", "clean_b"], ["report"]]
    assert topological_order(wf) == ["extract", "clean_a", "clean_b", "report"]


def test_cycle_detection_raises():
    wf = Workflow()
    wf.add_task(Task(name="a", function=dummy_fn, dependencies=["c"]))
    wf.add_task(Task(name="b", function=dummy_fn, dependencies=["a"]))
    wf.add_task(Task(name="c", function=dummy_fn, dependencies=["b"]))

    with pytest.raises(WorkflowValidationError, match="cykl"):
        wf.validate()

    with pytest.raises(WorkflowValidationError, match="cykl"):
        topological_order(wf)