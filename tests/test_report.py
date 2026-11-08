from types import MappingProxyType

from pyflow import (
    RunResult,
    Task,
    TaskExecutionError,
    TaskState,
    TaskStatus,
    Workflow,
    format_report,
    run,
)


def make_result(states, outputs=None, started_at=0.0, finished_at=0.010):
    return RunResult(
        outputs=MappingProxyType(outputs or {}),
        task_states=MappingProxyType({state.name: state for state in states}),
        started_at=started_at,
        finished_at=finished_at,
    )


def test_report_lists_each_task_with_duration_and_total():
    result = make_result(
        [
            TaskState("extract", TaskStatus.SUCCEEDED, started_at=0.001, finished_at=0.003),
            TaskState("report", TaskStatus.SUCCEEDED, started_at=0.003, finished_at=0.007),
        ]
    )

    text = format_report(result)
    lines = text.splitlines()

    assert any(l.startswith("extract") and "SUCCEEDED" in l and l.endswith("2.000") for l in lines)
    assert any(l.startswith("report") and "SUCCEEDED" in l and l.endswith("4.000") for l in lines)
    assert "Suma czasów zadań:  6.000 ms" in text
    assert "Cały przebieg:      10.000 ms" in text
    assert "SUKCES (2/2" in text


def test_report_shows_error_and_skip_reason():
    error = TaskExecutionError("load", ValueError("zły plik"))
    result = make_result(
        [
            TaskState("load", TaskStatus.FAILED, started_at=0.0, finished_at=0.001, error=error),
            TaskState("save", TaskStatus.SKIPPED, skip_reason="zależności: load (FAILED)"),
        ]
    )

    text = format_report(result)
    save_line = next(l for l in text.splitlines() if l.startswith("save"))

    assert save_line.rstrip().endswith("-")  # pominięte zadanie nie ma czasu
    assert "błąd: Zadanie 'load' zakończyło się błędem ValueError: zły plik" in text
    assert "pominięto: zależności: load (FAILED)" in text
    assert "BŁĄD (nieudane: 1, pominięte: 1, wszystkich: 2)" in text


def test_report_for_empty_workflow():
    text = format_report(run(Workflow()))

    assert "Cały przebieg:" in text
    assert "SUKCES (0/0" in text


def test_report_does_not_change_result():
    wf = Workflow()
    wf.add_task(Task("a", lambda i, p: [1, 2, 3]))
    result = run(wf)
    outputs_before = dict(result.outputs)
    states_before = dict(result.task_states)

    format_report(result)

    assert dict(result.outputs) == outputs_before
    assert dict(result.task_states) == states_before
