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


def test_snowflake_decodes_millisecond_timestamp_field():
    epoch_ms = 1420070400000
    result = decode_timestamp({"event_id": "d", "format": "snowflake", "raw_value": "0"})
    assert result.point_ns == epoch_ms * 1_000_000
    assert result.storage_granularity_ns == 1_000_000


@pytest.mark.parametrize("raw", ["-1", str(1 << 64), "abc"])
def test_snowflake_rejects_invalid_unsigned_64_bit_ids(raw):
    with pytest.raises(ValueError):
        decode_timestamp({"event_id": "d", "format": "snowflake", "raw_value": raw})
