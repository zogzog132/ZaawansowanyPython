"""Tekstowy raport przebiegu z czasami wykonania.

Raport jest wyłącznie widokiem na ``RunResult`` – tylko odczytuje dane i niczego w nich
nie zmienia (wynik jest zresztą niemutowalny).
"""

from pyflow.results import RunResult, TaskStatus

_NAME_HEADER = "Zadanie"
_STATUS_HEADER = "Status"
_TIME_HEADER = "Czas [ms]"
_STATUS_WIDTH = max(len(_STATUS_HEADER), *(len(status.value) for status in TaskStatus))
_TIME_WIDTH = len(_TIME_HEADER)


def format_report(result: RunResult) -> str:
    """Zwraca raport: status i czas każdego zadania, suma czasów zadań i czas całego przebiegu."""
    name_width = max([len(_NAME_HEADER), *(len(name) for name in result.task_states)])
    header = (
        f"{_NAME_HEADER:<{name_width}}  {_STATUS_HEADER:<{_STATUS_WIDTH}}  "
        f"{_TIME_HEADER:>{_TIME_WIDTH}}"
    )
    rule = "-" * len(header)

    lines = ["Raport przebiegu PyFlow", "=" * len(header), header, rule]

    for name, state in result.task_states.items():
        duration = "-" if state.duration is None else _ms(state.duration)
        lines.append(
            f"{name:<{name_width}}  {state.status.value:<{_STATUS_WIDTH}}  "
            f"{duration:>{_TIME_WIDTH}}"
        )
        if state.error is not None:
            lines.append(f"    -> błąd: {state.error}")
        if state.skip_reason is not None:
            lines.append(f"    -> pominięto: {state.skip_reason}")

    tasks_total = sum(
        state.duration for state in result.task_states.values() if state.duration is not None
    )
    lines.append(rule)
    lines.append(f"Suma czasów zadań:  {_ms(tasks_total)} ms")
    lines.append(f"Cały przebieg:      {_ms(result.duration)} ms")
    lines.append(f"Wynik: {_summary(result)}")
    return "\n".join(lines)


def _ms(seconds: float) -> str:
    return f"{seconds * 1000:.3f}"


def _summary(result: RunResult) -> str:
    total = len(result.task_states)
    if result.succeeded:
        return f"SUKCES ({total}/{total} zadań zakończonych sukcesem)"
    return (
        f"BŁĄD (nieudane: {len(result.failed_tasks)}, "
        f"pominięte: {len(result.skipped_tasks)}, wszystkich: {total})"
    )
