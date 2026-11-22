"""Integer-only UTC interval normalization and comparison."""

from datetime import datetime, timedelta, timezone

from verity.models import ComparisonResult, DecodedTimestamp, TimestampInterval

TARGET_MIN_NS = -(1 << 63)
TARGET_MAX_NS = (1 << 63) - 1
NANOSECONDS_PER_SECOND = 1_000_000_000


def normalize_timestamp(
    point_ns: int,
    resolution_ns: int,
    *,
    actual_resolution_ns: int | None = None,
) -> TimestampInterval:
    """Normalize a source point to its closed interval on the UTC ns grid."""
    resolution = actual_resolution_ns if actual_resolution_ns is not None else resolution_ns
    if resolution <= 0:
        raise ValueError("timestamp resolution must be positive")
    end_ns = point_ns + resolution - 1
    if point_ns < TARGET_MIN_NS or end_ns > TARGET_MAX_NS:
        raise ValueError("normalized interval is outside the VERITY target domain")
    return TimestampInterval(point_ns, end_ns)


def normalize_decoded(timestamp: DecodedTimestamp) -> TimestampInterval:
    return normalize_timestamp(
        timestamp.point_ns,
        timestamp.storage_granularity_ns,
        actual_resolution_ns=timestamp.actual_resolution_ns,
    )


def compare_intervals(
    first: TimestampInterval, second: TimestampInterval
) -> tuple[bool, bool]:
    """Return each direction of the paper's weak-precedence relation."""
    return first.end_ns <= second.start_ns, second.end_ns <= first.start_ns


def compare_with_explanation(
    first: TimestampInterval,
    second: TimestampInterval,
    first_event_id: str | None = None,
    second_event_id: str | None = None,
) -> ComparisonResult:
    first_precedes, second_precedes = compare_intervals(first, second)

    first_name = f"Event '{first_event_id}'" if first_event_id else "The first timestamp"
    second_name = f"event '{second_event_id}'" if second_event_id else "the second timestamp"

    if first_precedes:
        explanation = (
            f"{first_name} precedes {second_name} because "
            "its interval ends at or before the second interval starts."
        )
    elif second_precedes:
        explanation = (
            f"{second_name.capitalize()} precedes {first_name.lower()} because "
            "its interval ends at or before the first interval starts."
        )
    else:
        explanation = (
            f"{first_name} and {second_name} overlap, "
            "so their order is undetermined at the available precision."
        )

    return ComparisonResult(first_precedes, second_precedes, explanation)


def format_utc_ns(value_ns: int) -> str:
    """Format a supported POSIX nanosecond instant as RFC 3339 with 9 digits."""
    if not TARGET_MIN_NS <= value_ns <= TARGET_MAX_NS:
        raise ValueError("instant is outside the VERITY target domain")
    seconds, nanoseconds = divmod(value_ns, NANOSECONDS_PER_SECOND)
    instant = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=seconds)
    return f"{instant:%Y-%m-%dT%H:%M:%S}.{nanoseconds:09d}Z"
