import json

from examples.sales_pipeline import DEFAULT_INPUT, build_workflow, main
from pyflow import TaskStatus, execution_layers, run

CSV_CONTENT = """\
date,region,product,quantity,unit_price
2026-10-01,Kraków,Mysz,2,50.00
2026-10-02,Kraków,Monitor,1,800.00
2026-10-03,Gdańsk,Mysz,3,50.00
2026-10-04,,Mysz,1,50.00
2026-10-05,Gdańsk,Monitor,zero,800.00
"""


def write_csv(tmp_path):
    path = tmp_path / "sales.csv"
    path.write_text(CSV_CONTENT, encoding="utf-8")
    return path


def test_csv_to_json_end_to_end(tmp_path):
    input_csv = write_csv(tmp_path)
    output_json = tmp_path / "out" / "report.json"

    result = run(build_workflow(input_csv, output_json))

    assert result.succeeded, result.errors
    assert result.outputs["write_json_report"] == str(output_json)

    report = json.loads(output_json.read_text(encoding="utf-8"))
    assert report["source"] == "sales.csv"
    assert report["records"] == {"total": 5, "valid": 3, "rejected": 2}
    assert [r["line"] for r in report["rejected"]] == [5, 6]
    assert "region" in report["rejected"][0]["reason"]
    assert "ilość" in report["rejected"][1]["reason"]
    assert report["by_region"] == {
        "Gdańsk": {"orders": 1, "quantity": 3, "revenue": 150.0},
        "Kraków": {"orders": 2, "quantity": 3, "revenue": 900.0},
    }
    assert report["by_product"] == {
        "Monitor": {"orders": 1, "quantity": 1, "revenue": 800.0},
        "Mysz": {"orders": 2, "quantity": 5, "revenue": 250.0},
    }
    assert report["totals"] == {"orders": 3, "quantity": 6, "revenue": 1050.0}


def test_workflow_shape_matches_expected_layers(tmp_path):
    wf = build_workflow(tmp_path / "in.csv", tmp_path / "out.json")

    assert execution_layers(wf) == [
        ["read_csv"],
        ["clean_records"],
        ["aggregate_by_product", "aggregate_by_region"],
        ["write_json_report"],
    ]


def test_output_is_deterministic(tmp_path):
    input_csv = write_csv(tmp_path)
    first, second = tmp_path / "first.json", tmp_path / "second.json"

    run(build_workflow(input_csv, first))
    run(build_workflow(input_csv, second))

    assert first.read_bytes() == second.read_bytes()


def test_missing_input_fails_and_skips_downstream(tmp_path):
    output_json = tmp_path / "report.json"

    result = run(build_workflow(tmp_path / "does_not_exist.csv", output_json))

    assert result.succeeded is False
    assert result.task_states["read_csv"].status is TaskStatus.FAILED
    assert isinstance(result.errors["read_csv"].__cause__, FileNotFoundError)
    assert result.skipped_tasks == [
        "clean_records",
        "aggregate_by_product",
        "aggregate_by_region",
        "write_json_report",
    ]
    assert not output_json.exists()


def test_bundled_example_data_runs(tmp_path, capsys):
    output_json = tmp_path / "report.json"

    exit_code = main([str(DEFAULT_INPUT), str(output_json)])

    assert exit_code == 0
    report = json.loads(output_json.read_text(encoding="utf-8"))
    assert report["records"] == {"total": 14, "valid": 9, "rejected": 5}
    assert report["totals"]["revenue"] == 5575.1
    printed = capsys.readouterr().out
    assert "Raport przebiegu PyFlow" in printed
    assert "Cały przebieg:" in printed
