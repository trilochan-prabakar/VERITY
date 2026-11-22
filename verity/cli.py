"""CSV command-line interface for VERITY."""

import argparse
import csv
from itertools import combinations
from pathlib import Path
import sys

from verity.normalization import compare_with_explanation, format_utc_ns
from verity.validation import validate_row

NORMALIZED_COLUMNS = [
    "normalized_start_utc",
    "normalized_end_utc",
    "normalized_storage_granularity_ns",
    "normalized_actual_resolution_ns",
    "normalization_resolution_ns",
    "normalized_validation_status",
    "normalized_explanation",
]
COMPARISON_COLUMNS = [
    "event_id_a",
    "event_id_b",
    "a_precedes_b",
    "b_precedes_a",
    "explanation",
]


def run_csv(input_path: str | Path, normalized_path: str | Path, comparisons_path: str | Path) -> int:
    """Read a batch, write normalized results and every resolvable pair."""
    with Path(input_path).open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames is None or not {"event_id", "format", "raw_value"}.issubset(reader.fieldnames):
            raise ValueError("input CSV must have event_id, format, and raw_value columns")
        input_columns = list(reader.fieldnames)
        rows = list(reader)
    if len(input_columns) != len(set(input_columns)):
        raise ValueError("input CSV column names must be unique")
    derived_columns = {}
    occupied_columns = set(input_columns)
    for column in NORMALIZED_COLUMNS:
        output_column = column
        while output_column in occupied_columns:
            output_column = f"verity_{output_column}"
        derived_columns[column] = output_column
        occupied_columns.add(output_column)
    identifiers = [row.get("event_id", "") for row in rows]
    if any(not event_id for event_id in identifiers):
        raise ValueError("every row must have a non-empty event_id")
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("event_id values must be unique")

    results = [validate_row(row) for row in rows]
    normalized_output = []
    for row, result in zip(rows, results):
        entry = dict(row)
        derived_values = {
            "normalized_start_utc": format_utc_ns(result.interval.start_ns) if result.interval else "",
            "normalized_end_utc": format_utc_ns(result.interval.end_ns) if result.interval else "",
            "normalized_storage_granularity_ns": str(result.decoded.storage_granularity_ns) if result.decoded else "",
            "normalized_actual_resolution_ns": (
                str(result.decoded.actual_resolution_ns)
                if result.decoded and result.decoded.actual_resolution_ns is not None else "unknown"
            ),
            "normalization_resolution_ns": (
                str(result.decoded.actual_resolution_ns or result.decoded.storage_granularity_ns)
                if result.decoded else ""
            ),
            "normalized_validation_status": result.status,
            "normalized_explanation": result.explanation,
        }
        entry.update({derived_columns[column]: value for column, value in derived_values.items()})
        normalized_output.append(entry)

    with Path(normalized_path).open("w", encoding="utf-8", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=input_columns + list(derived_columns.values()))
        writer.writeheader()
        writer.writerows(normalized_output)

    comparable = [(row["event_id"], result.interval) for row, result in zip(rows, results) if result.interval]
    with Path(comparisons_path).open("w", encoding="utf-8", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=COMPARISON_COLUMNS)
        writer.writeheader()
        for (first_id, first_interval), (second_id, second_interval) in combinations(comparable, 2):
            comparison = compare_with_explanation(first_interval,second_interval,first_event_id=first_id,second_event_id=second_id,)
            writer.writerow({
                "event_id_a": first_id,
                "event_id_b": second_id,
                "a_precedes_b": str(comparison.first_precedes_second).lower(),
                "b_precedes_a": str(comparison.second_precedes_first).lower(),
                "explanation": comparison.explanation,
            })
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Normalize and compare forensic timestamps from CSV.")
    parser.add_argument("input_csv", help="CSV with event_id, format, and raw_value columns")
    parser.add_argument("-o", "--output", default="normalized.csv", help="normalized output CSV")
    parser.add_argument("-c", "--comparisons", default="comparisons.csv", help="pairwise comparison CSV")
    arguments = parser.parse_args(argv)
    try:
        return run_csv(arguments.input_csv, arguments.output, arguments.comparisons)
    except (OSError, csv.Error, ImportError, ValueError) as error:
        print(f"verity: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
