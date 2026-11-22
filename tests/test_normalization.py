import pytest

from verity.models import TimestampInterval
from verity.normalization import (
    compare_intervals,
    compare_with_explanation,
    format_utc_ns,
    normalize_timestamp,
)


def test_normalization_preserves_closed_interval_resolution():
    result = normalize_timestamp(100, 100)
    assert result == TimestampInterval(start_ns=100, end_ns=199)


def test_explicit_resolution_overrides_formal_domain_resolution():
    result = normalize_timestamp(100, 100, actual_resolution_ns=1_000_000_000)
    assert result.end_ns == 100 + 1_000_000_000 - 1


def test_intervals_touching_at_boundary_weakly_precede_in_one_direction():
    assert compare_intervals(TimestampInterval(1, 2), TimestampInterval(2, 9)) == (True, False)


def test_overlapping_intervals_are_undetermined():
    assert compare_intervals(TimestampInterval(1, 4), TimestampInterval(3, 8)) == (False, False)


def test_comparison_explains_when_first_interval_precedes_second():
    result = compare_with_explanation(TimestampInterval(1, 2), TimestampInterval(5, 8))
    assert result.first_precedes_second is True
    assert result.second_precedes_first is False
    assert "its interval ends at or before the second interval starts" in result.explanation


def test_comparison_explains_when_second_interval_precedes_first():
    result = compare_with_explanation(TimestampInterval(5, 8), TimestampInterval(1, 2))
    assert result.first_precedes_second is False
    assert result.second_precedes_first is True
    assert "its interval ends at or before the first interval starts" in result.explanation


def test_comparison_explains_when_intervals_overlap():
    result = compare_with_explanation(TimestampInterval(1, 4), TimestampInterval(3, 8))
    assert result.first_precedes_second is False
    assert result.second_precedes_first is False
    assert "overlap" in result.explanation


def test_separated_intervals_can_precede_in_either_direction():
    left, right = TimestampInterval(1, 2), TimestampInterval(5, 8)
    assert compare_intervals(left, right) == (True, False)
    assert compare_intervals(right, left) == (False, True)


def test_target_domain_end_is_not_clamped():
    with pytest.raises(ValueError, match="target domain"):
        normalize_timestamp((1 << 63) - 1, 2)


def test_normalization_accepts_exact_target_domain_boundaries():
    minimum = normalize_timestamp(-(1 << 63), 1)
    maximum = normalize_timestamp((1 << 63) - 1, 1)
    assert minimum == TimestampInterval(-(1 << 63), -(1 << 63))
    assert maximum == TimestampInterval((1 << 63) - 1, (1 << 63) - 1)


def test_normalization_rejects_interval_start_below_target_domain():
    with pytest.raises(ValueError, match="target domain"):
        normalize_timestamp(-(1 << 63) - 1, 1)


def test_utc_formatter_emits_nine_digits_and_handles_pre_epoch():
    assert format_utc_ns(-1) == "1969-12-31T23:59:59.999999999Z"
