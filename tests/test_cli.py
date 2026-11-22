import csv

from verity.cli import run_csv


def test_csv_run_preserves_input_and_writes_pairwise_comparisons(tmp_path):
    source = tmp_path / "input.csv"
    normalized = tmp_path / "normalized.csv"
    comparisons = tmp_path / "comparisons.csv"
    source.write_text("event_id,format,raw_value,note\na,apfs,0,kept\nb,apfs,1,also kept\n", encoding="utf-8")

    assert run_csv(source, normalized, comparisons) == 0
    with normalized.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert [row["note"] for row in rows] == ["kept", "also kept"]
    assert rows[0]["raw_value"] == "0"
    with comparisons.open(encoding="utf-8", newline="") as stream:
        pairs = list(csv.DictReader(stream))
    assert len(pairs) == 1
    assert pairs[0]["event_id_a"] == "a"
    assert pairs[0]["a_precedes_b"] == "true"
    assert pairs[0]["b_precedes_a"] == "false"


def test_invalid_row_is_written_as_unresolved_with_reason(tmp_path):
    source = tmp_path / "input.csv"
    normalized = tmp_path / "normalized.csv"
    comparisons = tmp_path / "comparisons.csv"
    source.write_text("event_id,format,raw_value\nbad,snowflake,-1\n", encoding="utf-8")
    run_csv(source, normalized, comparisons)
    with normalized.open(encoding="utf-8", newline="") as stream:
        row = next(csv.DictReader(stream))
    assert row["normalized_validation_status"] == "unresolved"
    assert "unsigned" in row["normalized_explanation"]


def test_valid_source_outside_target_domain_retains_format_metadata(tmp_path):
    source = tmp_path / "input.csv"
    normalized = tmp_path / "normalized.csv"
    comparisons = tmp_path / "comparisons.csv"
    source.write_text("event_id,format,raw_value,actual_resolution_ns\nlate,apfs,9223372036854775807,2\n", encoding="utf-8")
    run_csv(source, normalized, comparisons)
    with normalized.open(encoding="utf-8", newline="") as stream:
        row = next(csv.DictReader(stream))
    assert row["normalized_validation_status"] == "unresolved"
    assert row["normalized_storage_granularity_ns"] == "1"
    assert "target domain" in row["normalized_explanation"]


def test_input_resolution_metadata_is_preserved_without_duplicate_headers(tmp_path):
    source = tmp_path / "input.csv"
    normalized = tmp_path / "normalized.csv"
    comparisons = tmp_path / "comparisons.csv"
    source.write_text("event_id,format,raw_value,actual_resolution_ns\na,apfs,0,3\n", encoding="utf-8")
    run_csv(source, normalized, comparisons)
    with normalized.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        row = next(reader)
        assert len(reader.fieldnames) == len(set(reader.fieldnames))
    assert row["actual_resolution_ns"] == "3"
    assert row["normalized_actual_resolution_ns"] == "3"
    assert row["normalization_resolution_ns"] == "3"


def test_short_csv_row_is_reported_unresolved(tmp_path):
    source = tmp_path / "input.csv"
    normalized = tmp_path / "normalized.csv"
    comparisons = tmp_path / "comparisons.csv"
    source.write_text("event_id,format,raw_value\nshort,apfs\n", encoding="utf-8")
    run_csv(source, normalized, comparisons)
    with normalized.open(encoding="utf-8", newline="") as stream:
        row = next(csv.DictReader(stream))
    assert row["normalized_validation_status"] == "unresolved"
    assert "raw_value is required" in row["normalized_explanation"]


def test_metadata_column_collision_gets_a_distinct_derived_column(tmp_path):
    source = tmp_path / "input.csv"
    normalized = tmp_path / "normalized.csv"
    comparisons = tmp_path / "comparisons.csv"
    source.write_text("event_id,format,raw_value,normalized_start_utc\na,apfs,0,source value\n", encoding="utf-8")
    run_csv(source, normalized, comparisons)
    with normalized.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        row = next(reader)
        assert len(reader.fieldnames) == len(set(reader.fieldnames))
    assert row["normalized_start_utc"] == "source value"
    assert row["verity_normalized_start_utc"] == "1970-01-01T00:00:00.000000000Z"
