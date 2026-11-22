# VERITY

VERITY is a small Python library and command-line tool for decoding selected forensic timestamps, mapping them to closed UTC intervals, and comparing intervals using weak precedence. It follows the timestamp model documented by Hornung et al. in TIME 2026. A normalized result represents the timestamps the source value could denote at its declared or modeled resolution; it does not establish the truth or integrity of the evidence.

## Requirements and install

VERITY targets Python 3.10 or newer and requires `dfDateTime` for APFS and FILETIME timestamp objects. Install in an environment with:

```bash
python -m pip install .
```

To run tests, install the optional test dependencies with `python -m pip install '.[test]'`, then run `python -m pytest`. To report coverage, run `python -m pytest --cov=verity --cov-report=term-missing`.

## CSV input

Every input CSV must have unique column names and include `event_id`, `format`, and `raw_value` columns. Each `event_id` must contain a non-whitespace character and be unique. Rows with missing or invalid `format` or `raw_value` values are retained as unresolved with an explanation. Short rows are also retained as unresolved; rows with extra CSV fields are rejected with a row-numbered error. VERITY copies all input columns and values to the normalized CSV. Optional columns include `actual_resolution_ns` for a known source clock resolution, `timestamp_kind` for exFAT and context-specific FILETIME semantics, plus the exFAT fields described below.

Supported format names are `apfs`, `filetime`, `exfat`, and `snowflake` (Discord Snowflake). Values are exact integers in decimal, with optional `0x` notation for fields that permit it.

| Format | `raw_value` and additional input | Storage granularity | Default normalization resolution |
| --- | --- | ---: | ---: |
| APFS | Signed 64-bit decimal nanoseconds since Unix epoch | 1 ns | 1 ns |
| NTFS FILETIME | Unsigned 64-bit decimal count of 100 ns units since 1601-01-01 UTC; zero means not set. `0xffffffff` in an access-time field is treated as the preserve-previous-access sentinel. | 100 ns | 100 ns |
| exFAT | `date_word:time_word`, each a 16-bit FAT field; decimal or `0x` notation. Requires `timestamp_kind` (`creation`, `modification`, or `access`) and `utc_offset_byte`. Creation/modification also require `increment` from 0 through 199. If the offset validity bit is clear, provide `utc_offset_minutes`. | 10 ms for creation/modification; 2 s for access | Same as storage unless `actual_resolution_ns` is supplied |
| Discord Snowflake | Unsigned 64-bit decimal ID; timestamp uses bits 63–22 and epoch 2015-01-01 UTC. Hexadecimal notation is not accepted. | 1 ms timestamp field | 1 ms |

APFS nanoseconds and FILETIME counts also require decimal notation. exFAT date and time words, and its UTC offset byte, accept decimal or `0x`-prefixed hexadecimal notation. Other numeric metadata uses decimal notation.

For an offset byte with its high validity bit set, the lower seven bits are a signed two's-complement count of 15-minute units. If the high bit is clear, the value is invalid and VERITY requires the explicit `utc_offset_minutes` metadata; no timezone is guessed. Access timestamps do not use an increment.

The source encoding's range and VERITY's signed 64-bit nanosecond target range are checked separately. FILETIME values may be valid source values but unresolved because their normalized interval is outside the target. Intervals are closed and use integer nanoseconds. No endpoint is clamped. Leap seconds are excluded under the POSIX timescale. Output endpoints are RFC 3339 UTC values with exactly nine fractional digits.

Discord's official format has a 42-bit timestamp field. TIME 2026 models Discord Snowflake with a 41-bit field; VERITY follows Discord's documented encoding and records that discrepancy here.

## Run the CLI

From the project directory:

```bash
python -m verity.cli examples/input.csv --output normalized.csv --comparisons comparisons.csv
```

After installation, the same command is available through the `verity` console script:

```bash
verity examples/input.csv --output normalized.csv --comparisons comparisons.csv
```

The normalized CSV preserves all input columns and appends these columns:

- `normalized_start_utc`, `normalized_end_utc`: closed interval endpoints, or empty for unresolved rows.
- `normalized_storage_granularity_ns`: source format granularity when decoding succeeded, or empty when decoding failed.
- `normalized_actual_resolution_ns`: supplied actual resolution when decoding succeeded, or `unknown` when absent or decoding failed.
- `normalization_resolution_ns`: the resolution used for interval construction, or empty when decoding failed.
- `normalized_validation_status`: `valid` or `unresolved`.
- `normalized_explanation`: explains the interval and resolution for successful normalization, or gives the reason an input is unresolved.

If an input column already has one of these derived names, VERITY prefixes that derived name with `verity_` (repeating the prefix if needed to avoid another collision).

The comparison CSV contains one row for every unordered pair of successfully normalized rows. Its columns are `event_id_a`, `event_id_b`, `a_precedes_b`, `b_precedes_a`, and `explanation`. The explanation describes the precedence relation when one interval precedes the other, or explains that the order is undetermined when the intervals overlap. For intervals `[a,b]` and `[c,d]`, the first precedes the second exactly when `b <= c`; boundary equality counts.

The CLI accepts the required positional `input_csv` path, `-o`/`--output` (default `normalized.csv`), and `-c`/`--comparisons` (default `comparisons.csv`). `-h`/`--help` displays usage.

For exFAT input:

```bash
python -m verity.cli examples/exfat.csv -o exfat-normalized.csv -c exfat-comparisons.csv
```

## Library use

```python
from verity import compare_intervals, decode_timestamp, normalize_timestamp

decoded = decode_timestamp({"event_id": "event-1", "format": "apfs", "raw_value": "1704067200000000000"})
interval = normalize_timestamp(decoded.point_ns, decoded.storage_granularity_ns)
print(interval)
```

`decode_timestamp` raises `ValueError` for invalid source data or missing required metadata. The CLI records these rows as unresolved with a reason. Pairwise comparisons are intended for small coursework batches; output size grows quadratically with the number of normalizable rows.

## Limitations

- Only the four explicit formats above are decoded. Arbitrary date strings and automatic timezone inference are not supported.
- Filetime semantics depend on the producer and field; declare an actual resolution only when known. The default is the paper's modeled source-domain resolution.
- exFAT decoding expects the packed FAT date/time words and required source metadata, not an entire disk image.
- Discord Snowflake values that decode beyond VERITY's target domain remain unresolved.
- This is a foundational coursework implementation, not a production forensic suite or a determination of evidentiary admissibility.

## References and attribution

- Hornung et al., [A Formal Model for Forensically Sound Timestamp Normalization](https://doi.org/10.4230/OASIcs.TIME.2026.10), TIME 2026.
- [`dfDateTime` timestamp value documentation](https://dfdatetime.readthedocs.io/en/latest/sources/Date-and-time-values.html) and [API](https://dfdatetime.readthedocs.io/en/latest/sources/api/dfdatetime.html).
- [Microsoft exFAT specification](https://learn.microsoft.com/en-us/windows/win32/fileio/exfat-specification).
- [Discord Snowflakes](https://discord.com/developers/docs/reference#snowflakes).

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for dependency attribution.
