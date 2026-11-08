import pytest
from pyflow import (
    Task,
    TaskExecutionError,
    TaskStatus,
    Workflow,
    WorkflowValidationError,
    run,
    topological_order,
)


def const(value):
    def fn(inputs, params):
        return value

    return fn


def fail_with(exc):
    def fn(inputs, params):
        raise exc

    return fn


def recording(log, name, value=None):
    def fn(inputs, params):
        log.append(name)
        return value

    return fn


# --- Przepływ wyników i parametry -------------------------------------------------------


def test_empty_workflow_returns_empty_successful_result():
    result = run(Workflow())

    assert result.succeeded is True
    assert dict(result.outputs) == {}
    assert dict(result.task_states) == {}
    assert result.failed_tasks == []
    assert result.duration >= 0


def test_single_task_output_and_status():
    wf = Workflow()
    wf.add_task(Task("only", const(42)))

    result = run(wf)

    assert result.succeeded is True
    assert result.outputs["only"] == 42
    assert result.task_states["only"].status is TaskStatus.SUCCEEDED


def test_task_receives_exactly_direct_dependency_outputs():
    seen_inputs = {}

    def capture(name, value):
        def fn(inputs, params):
            seen_inputs[name] = dict(inputs)
            return value

        return fn

    wf = Workflow()
    wf.add_task(Task("a", capture("a", "A")))
    wf.add_task(Task("b", capture("b", "B"), dependencies=["a"]))
    wf.add_task(Task("c", capture("c", "C"), dependencies=["b"]))

    run(wf)

    assert seen_inputs["a"] == {}
    assert seen_inputs["b"] == {"a": "A"}
    assert seen_inputs["c"] == {"b": "B"}  # bez przechodniej zależności "a"


def test_results_flow_through_diamond():
    wf = Workflow()
    wf.add_task(Task("extract", const(10)))
    wf.add_task(Task("clean_a", lambda i, p: i["extract"] + 1, ["extract"]))
    wf.add_task(Task("clean_b", lambda i, p: i["extract"] * 2, ["extract"]))
    wf.add_task(Task("report", lambda i, p: i["clean_a"] + i["clean_b"], ["clean_a", "clean_b"]))

    result = run(wf)

    assert dict(result.outputs) == {"extract": 10, "clean_a": 11, "clean_b": 20, "report": 31}


def test_params_are_passed_to_function():
    wf = Workflow()
    wf.add_task(Task("scale", lambda i, p: p["factor"] * 3, params={"factor": 5}))

    assert run(wf).outputs["scale"] == 15


def test_inputs_and_params_are_read_only_for_task():
    def try_to_mutate(inputs, params):
        with pytest.raises(TypeError):
            inputs["new"] = 1  # type: ignore[index]
        with pytest.raises(TypeError):
            params["new"] = 1  # type: ignore[index]
        return "ok"

    wf = Workflow()
    wf.add_task(Task("source", const(1)))
    wf.add_task(Task("t", try_to_mutate, ["source"], {"x": 1}))

    assert run(wf).outputs["t"] == "ok"


# --- Kolejność wykonania ---------------------------------------------------------------


def test_execution_order_follows_topological_plan():
    log = []
    wf = Workflow()
    wf.add_task(Task("report", recording(log, "report"), ["clean_a", "clean_b"]))
    wf.add_task(Task("clean_b", recording(log, "clean_b"), ["extract"]))
    wf.add_task(Task("clean_a", recording(log, "clean_a"), ["extract"]))
    wf.add_task(Task("extract", recording(log, "extract")))

    result = run(wf)

    assert log == topological_order(wf) == ["extract", "clean_a", "clean_b", "report"]
    assert list(result.task_states) == log


def test_invalid_workflow_raises_before_any_task_runs():
    log = []
    wf = Workflow()
    wf.add_task(Task("a", recording(log, "a"), ["b"]))
    wf.add_task(Task("b", recording(log, "b"), ["a"]))
    wf.add_task(Task("free", recording(log, "free")))

    with pytest.raises(WorkflowValidationError, match="cykl"):
        run(wf)
    assert log == []


# --- Awaria zadania i polityka błędów (kontynuacja niezależnych zadań) -----------------


def test_failed_task_has_status_and_chained_error():
    original = ValueError("zła wartość")
    wf = Workflow()
    wf.add_task(Task("a", const(1)))
    wf.add_task(Task("b", fail_with(original), ["a"]))

    result = run(wf)

    state = result.task_states["b"]
    assert result.succeeded is False
    assert state.status is TaskStatus.FAILED
    assert isinstance(state.error, TaskExecutionError)
    assert state.error.task_name == "b"
    assert state.error.__cause__ is original
    assert "b" in str(state.error) and "ValueError" in str(state.error)
    assert "b" not in result.outputs
    assert result.outputs["a"] == 1
    assert result.failed_tasks == ["b"]
    assert result.errors == {"b": state.error}


def test_dependents_of_failed_task_are_skipped_transitively():
    log = []
    wf = Workflow()
    wf.add_task(Task("a", fail_with(RuntimeError("x"))))
    wf.add_task(Task("b", recording(log, "b"), ["a"]))
    wf.add_task(Task("c", recording(log, "c"), ["b"]))

    result = run(wf)

    assert log == []  # funkcje pominiętych zadań nie są wywoływane
    assert result.task_states["a"].status is TaskStatus.FAILED
    assert result.task_states["b"].status is TaskStatus.SKIPPED
    assert result.task_states["c"].status is TaskStatus.SKIPPED
    assert "a (FAILED)" in result.task_states["b"].skip_reason
    assert "b (SKIPPED)" in result.task_states["c"].skip_reason
    assert result.skipped_tasks == ["b", "c"]
    assert result.task_states["b"].error is None


def test_task_with_one_failed_dependency_is_skipped():
    wf = Workflow()
    wf.add_task(Task("ok", const(1)))
    wf.add_task(Task("bad", fail_with(RuntimeError("x"))))
    wf.add_task(Task("join", const("never"), ["ok", "bad"]))

    result = run(wf)

    assert result.task_states["join"].status is TaskStatus.SKIPPED
    assert "bad (FAILED)" in result.task_states["join"].skip_reason
    assert "ok" not in result.task_states["join"].skip_reason


def test_independent_tasks_still_run_after_failure():
    log = []
    wf = Workflow()
    wf.add_task(Task("a_fails", fail_with(RuntimeError("x"))))  # alfabetycznie pierwsze
    wf.add_task(Task("b_independent", recording(log, "b_independent", "B")))
    wf.add_task(Task("c_after", recording(log, "c_after", "C"), ["b_independent"]))

    result = run(wf)

    assert log == ["b_independent", "c_after"]
    assert result.task_states["b_independent"].status is TaskStatus.SUCCEEDED
    assert result.task_states["c_after"].status is TaskStatus.SUCCEEDED
    assert result.outputs["c_after"] == "C"
    assert result.succeeded is False


def test_raise_for_failure_raises_execution_error_with_cause():
    original = KeyError("brak")
    wf = Workflow()
    wf.add_task(Task("broken", fail_with(original)))

    result = run(wf)

    with pytest.raises(TaskExecutionError, match="broken") as info:
        result.raise_for_failure()
    assert info.value.task_name == "broken"
    assert info.value.__cause__ is original


def test_raise_for_failure_does_nothing_on_success():
    wf = Workflow()
    wf.add_task(Task("a", const(1)))

    run(wf).raise_for_failure()


def test_keyboard_interrupt_is_not_swallowed():
    wf = Workflow()
    wf.add_task(Task("a", fail_with(KeyboardInterrupt())))

    with pytest.raises(KeyboardInterrupt):
        run(wf)


# --- Czasy i niemutowalność wyniku ----------------------------------------------------


def test_timings_are_recorded_for_executed_tasks_only():
    wf = Workflow()
    wf.add_task(Task("a", const(1)))
    wf.add_task(Task("b", fail_with(RuntimeError("x")), ["a"]))
    wf.add_task(Task("c", const(3), ["b"]))

    result = run(wf)

    for name in ("a", "b"):
        state = result.task_states[name]
        assert state.started_at is not None and state.finished_at is not None
        assert state.duration >= 0
    assert result.task_states["c"].duration is None
    executed_total = sum(result.task_states[n].duration for n in ("a", "b"))
    assert result.duration >= executed_total


def test_result_is_read_only():
    wf = Workflow()
    wf.add_task(Task("a", const(1)))
    result = run(wf)

    with pytest.raises(TypeError):
        result.outputs["a"] = 2  # type: ignore[index]
    with pytest.raises(TypeError):
        result.task_states["a"] = None  # type: ignore[index]
