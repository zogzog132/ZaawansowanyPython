"""Przykład end-to-end: CSV -> walidacja -> agregacje -> raport JSON.

Graf zadań:

    read_csv -> clean_records -> aggregate_by_region  -> write_json_report
                              -> aggregate_by_product ->

Uruchomienie z katalogu głównego repozytorium:

    python -m examples.sales_pipeline
    python -m examples.sales_pipeline wejscie.csv wyjscie.json

Przykład jest deterministyczny i nie wymaga dostępu do sieci.
"""

import argparse
import csv
import json
import sys
from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from pyflow import Task, Workflow, format_report, run

EXAMPLES_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT = EXAMPLES_DIR / "data" / "sales.csv"
DEFAULT_OUTPUT = EXAMPLES_DIR / "output" / "sales_report.json"

REQUIRED_FIELDS = ("date", "region", "product", "quantity", "unit_price")
CENTS = Decimal("0.01")


# --- Funkcje zadań: każda ma postać function(inputs, params) ---------------------------


def read_csv(inputs: Mapping[str, Any], params: Mapping[str, Any]) -> list[dict[str, str]]:
    """Wczytuje plik CSV (UTF-8) jako listę słowników."""
    with open(params["path"], encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def clean_records(inputs: Mapping[str, Any], params: Mapping[str, Any]) -> dict[str, Any]:
    """Waliduje i typuje rekordy; błędne rekordy trafiają do listy ``rejected`` z powodem."""
    rows = inputs["read_csv"]
    valid: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    # Linia 1 to nagłówek, więc pierwszy rekord danych jest w linii 2.
    for line, row in enumerate(rows, start=2):
        try:
            valid.append(_parse_row(row))
        except ValueError as error:
            rejected.append({"line": line, "reason": str(error)})

    return {"total": len(rows), "valid": valid, "rejected": rejected}


def aggregate(inputs: Mapping[str, Any], params: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Agreguje poprawne rekordy po polu wskazanym w ``params["group_by"]``."""
    key = params["group_by"]
    groups: dict[str, dict[str, Any]] = {}

    for record in inputs["clean_records"]["valid"]:
        group = groups.setdefault(
            record[key], {"orders": 0, "quantity": 0, "revenue": Decimal("0")}
        )
        group["orders"] += 1
        group["quantity"] += record["quantity"]
        group["revenue"] += record["quantity"] * record["unit_price"]

    return {
        name: {**values, "revenue": _money(values["revenue"])}
        for name, values in sorted(groups.items())
    }


def write_json_report(inputs: Mapping[str, Any], params: Mapping[str, Any]) -> str:
    """Składa raport z wyników zależności, zapisuje go jako JSON i zwraca ścieżkę pliku."""
    cleaned = inputs["clean_records"]
    valid = cleaned["valid"]

    report = {
        "source": params["source"],
        "records": {
            "total": cleaned["total"],
            "valid": len(valid),
            "rejected": len(cleaned["rejected"]),
        },
        "rejected": cleaned["rejected"],
        "by_region": inputs["aggregate_by_region"],
        "by_product": inputs["aggregate_by_product"],
        "totals": {
            "orders": len(valid),
            "quantity": sum(record["quantity"] for record in valid),
            "revenue": _money(sum((r["quantity"] * r["unit_price"] for r in valid), Decimal("0"))),
        },
    }

    output_path = Path(params["output_path"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2, sort_keys=True)
        file.write("\n")
    return str(output_path)


# --- Definicja workflowu --------------------------------------------------------------


def build_workflow(input_csv: str | Path, output_json: str | Path) -> Workflow:
    workflow = Workflow()
    workflow.add_task(
        Task("read_csv", read_csv, params={"path": str(input_csv)}, description="Odczyt CSV")
    )
    workflow.add_task(
        Task("clean_records", clean_records, ["read_csv"], description="Walidacja rekordów")
    )
    workflow.add_task(
        Task("aggregate_by_region", aggregate, ["clean_records"], {"group_by": "region"})
    )
    workflow.add_task(
        Task("aggregate_by_product", aggregate, ["clean_records"], {"group_by": "product"})
    )
    workflow.add_task(
        Task(
            "write_json_report",
            write_json_report,
            ["clean_records", "aggregate_by_region", "aggregate_by_product"],
            {"output_path": str(output_json), "source": Path(input_csv).name},
            description="Zapis raportu JSON",
        )
    )
    return workflow


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Przykład PyFlow: CSV -> raport JSON.")
    parser.add_argument("input_csv", nargs="?", default=DEFAULT_INPUT, type=Path)
    parser.add_argument("output_json", nargs="?", default=DEFAULT_OUTPUT, type=Path)
    args = parser.parse_args(argv)

    result = run(build_workflow(args.input_csv, args.output_json))
    print(format_report(result))
    if result.succeeded:
        print(f"\nRaport JSON zapisano w: {result.outputs['write_json_report']}")
        return 0
    return 1


# --- Funkcje pomocnicze ---------------------------------------------------------------


def _parse_row(row: Mapping[str, str | None]) -> dict[str, Any]:
    for field in REQUIRED_FIELDS:
        if not (row.get(field) or "").strip():
            raise ValueError(f"brak wartości w polu '{field}'")

    try:
        sale_date = date.fromisoformat(row["date"].strip())
    except ValueError:
        raise ValueError(f"niepoprawna data '{row['date']}'") from None

    try:
        quantity = int(row["quantity"])
    except ValueError:
        raise ValueError(f"niepoprawna ilość '{row['quantity']}'") from None
    if quantity <= 0:
        raise ValueError(f"ilość musi być dodatnia, otrzymano {quantity}")

    try:
        unit_price = Decimal(row["unit_price"].strip())
    except InvalidOperation:
        raise ValueError(f"niepoprawna cena '{row['unit_price']}'") from None
    if not unit_price.is_finite() or unit_price <= 0:
        raise ValueError(f"cena musi być dodatnia, otrzymano {row['unit_price']}")

    return {
        "date": sale_date,
        "region": row["region"].strip(),
        "product": row["product"].strip(),
        "quantity": quantity,
        "unit_price": unit_price,
    }


def _money(value: Decimal) -> float:
    return float(value.quantize(CENTS))


if __name__ == "__main__":
    sys.exit(main())
