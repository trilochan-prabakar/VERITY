"""Decode and check the representability of one source timestamp."""

from dataclasses import dataclass

from verity.formats import decode_timestamp
from verity.models import DecodedTimestamp, TimestampInterval
from verity.normalization import format_utc_ns, normalize_decoded


@dataclass(frozen=True)
class ValidationResult:
    decoded: DecodedTimestamp | None
    interval: TimestampInterval | None
    status: str
    explanation: str


def validate_row(row: dict[str, str]) -> ValidationResult:
    decoded = None
    try:
        decoded = decode_timestamp(row)
        interval = normalize_decoded(decoded)
    except (ValueError, OverflowError) as error:
        return ValidationResult(decoded, None, "unresolved", str(error))
    if interval.start_ns > interval.end_ns:
        return ValidationResult(decoded, None, "unresolved", "normalized interval is empty")
    resolution = (
        decoded.actual_resolution_ns
        if decoded.actual_resolution_ns is not None
        else decoded.storage_granularity_ns
    )

    explanation = (
        f"Normalized to the closed UTC interval "
        f"[{format_utc_ns(interval.start_ns)}, {format_utc_ns(interval.end_ns)}] "
        f"using a resolution of {resolution} ns."
    )

    return ValidationResult(decoded, interval, "valid", explanation)
