import pytest

from verity.formats import decode_timestamp


def test_apfs_preserves_signed_nanosecond_value():
    result = decode_timestamp({"event_id": "a", "format": "apfs", "raw_value": "-1"})
    assert (result.point_ns, result.storage_granularity_ns, result.actual_resolution_ns) == (-1, 1, None)


def test_filetime_converts_epoch_and_retains_source_resolution():
    result = decode_timestamp({"event_id": "f", "format": "filetime", "raw_value": "116444736000000001"})
    assert result.point_ns == 100
    assert result.storage_granularity_ns == 100
    assert result.actual_resolution_ns is None


def test_filetime_rejects_special_zero_sentinel():
    with pytest.raises(ValueError, match="not set"):
        decode_timestamp({"event_id": "f", "format": "filetime", "raw_value": "0"})


def test_filetime_accepts_lowest_set_value_and_unsigned_upper_boundary():
    lowest = decode_timestamp({"event_id": "f", "format": "filetime", "raw_value": "1"})
    upper = decode_timestamp({"event_id": "f", "format": "filetime", "raw_value": str((1 << 64) - 1)})
    assert lowest.point_ns == (1 - 116_444_736_000_000_000) * 100
    assert upper.point_ns == (((1 << 64) - 1) - 116_444_736_000_000_000) * 100


def test_filetime_access_preserve_previous_sentinel_is_rejected():
    with pytest.raises(ValueError, match="preserve the previous access time"):
        decode_timestamp({"event_id": "f", "format": "filetime", "raw_value": "4294967295",
                          "timestamp_kind": "access"})


def test_exfat_applies_increment_and_valid_utc_offset():
    # 2024-01-01 00:00:00 local, UTC offset +1 hour, increment 5 x 10 ms.
    row = {"event_id": "e", "format": "exfat", "raw_value": "0x5821:0x0000",
           "timestamp_kind": "creation", "increment": "5", "utc_offset_byte": "0x84"}
    result = decode_timestamp(row)
    assert result.point_ns == 1704067200050000000 - 3600_000_000_000
    assert result.storage_granularity_ns == 10_000_000
    assert result.actual_resolution_ns is None
    assert result.source_metadata["utc_offset_byte"] == "0x84"


def test_exfat_requires_offset_when_validity_bit_is_clear():
    row = {"event_id": "e", "format": "exfat", "raw_value": "0x5821:0x0000",
           "timestamp_kind": "access", "utc_offset_byte": "0x04"}
    with pytest.raises(ValueError, match="offset"):
        decode_timestamp(row)


def test_exfat_accepts_calendar_and_increment_boundaries():
    # 1980-01-01 00:00:00 and 2107-12-31 23:59:58, with maximum creation increment.
    earliest = decode_timestamp({"event_id": "early", "format": "exfat", "raw_value": "33:0",
                                 "timestamp_kind": "creation", "increment": "0",
                                 "utc_offset_byte": "0x80"})
    latest = decode_timestamp({"event_id": "late", "format": "exfat", "raw_value": "65439:49021",
                               "timestamp_kind": "modification", "increment": "199",
                               "utc_offset_byte": "0x80"})
    assert earliest.point_ns == 315_532_800_000_000_000
    assert latest.storage_granularity_ns == 10_000_000
    assert latest.point_ns == (4_354_819_198 * 1_000_000_000) + 1_990_000_000


@pytest.mark.parametrize(
    ("raw", "extra", "message"),
    [
        ("65536:0", {"timestamp_kind": "access", "utc_offset_byte": "128"}, "16-bit"),
        ("33:65536", {"timestamp_kind": "access", "utc_offset_byte": "128"}, "16-bit"),
        ("1:0", {"timestamp_kind": "access", "utc_offset_byte": "128"}, "calendar"),
        ("33:0", {"timestamp_kind": "creation", "increment": "200", "utc_offset_byte": "128"}, "increment"),
        ("33:0", {"timestamp_kind": "modification", "increment": "0x1", "utc_offset_byte": "128"}, "integer"),
        ("33:0", {"timestamp_kind": "access", "utc_offset_byte": "0", "utc_offset_minutes": "946"}, "between -960 and 945"),
    ],
)
def test_exfat_rejects_invalid_field_ranges_and_metadata(raw, extra, message):
    row = {"event_id": "e", "format": "exfat", "raw_value": raw, **extra}
    with pytest.raises(ValueError, match=message):
        decode_timestamp(row)


@pytest.mark.parametrize("raw", ["0x1", "0X10"])
@pytest.mark.parametrize("fmt", ["apfs", "filetime", "snowflake"])
def test_decimal_only_formats_reject_hexadecimal_input(fmt, raw):
    with pytest.raises(ValueError, match="integer"):
        decode_timestamp({"event_id": "n", "format": fmt, "raw_value": raw})


@pytest.mark.parametrize(
    ("fmt", "raw"),
    [("apfs", str(-(1 << 63))), ("apfs", str((1 << 63) - 1)),
     ("filetime", "1"), ("filetime", str((1 << 64) - 1)),
     ("snowflake", "0"), ("snowflake", str((1 << 64) - 1))],
)
def test_integer_format_boundaries_are_accepted(fmt, raw):
    assert decode_timestamp({"event_id": "n", "format": fmt, "raw_value": raw})


@pytest.mark.parametrize(
    ("fmt", "raw"),
    [("apfs", str(-(1 << 63) - 1)), ("apfs", str(1 << 63)),
     ("filetime", str(1 << 64)), ("snowflake", str(1 << 64))],
)
def test_integer_format_out_of_range_boundaries_are_rejected(fmt, raw):
    with pytest.raises(ValueError, match="64-bit"):
        decode_timestamp({"event_id": "n", "format": fmt, "raw_value": raw})


def test_snowflake_decodes_millisecond_timestamp_field():
    epoch_ms = 1420070400000
    result = decode_timestamp({"event_id": "d", "format": "snowflake", "raw_value": "0"})
    assert result.point_ns == epoch_ms * 1_000_000
    assert result.storage_granularity_ns == 1_000_000


@pytest.mark.parametrize("raw", ["-1", str(1 << 64), "abc"])
def test_snowflake_rejects_invalid_unsigned_64_bit_ids(raw):
    with pytest.raises(ValueError):
        decode_timestamp({"event_id": "d", "format": "snowflake", "raw_value": raw})
