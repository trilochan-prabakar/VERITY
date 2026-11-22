"""Narrow decoders for the four timestamp formats in the V1 design."""

from datetime import datetime, timezone
import re

from verity.models import DecodedTimestamp

FILETIME_EPOCH_DELTA = 116_444_736_000_000_000
UINT64_MAX = (1 << 64) - 1
INT64_MIN = -(1 << 63)
INT64_MAX = (1 << 63) - 1
SNOWFLAKE_EPOCH_MS = 1_420_070_400_000
NANOSECONDS_PER_MILLISECOND = 1_000_000


def _integer(value: str, label: str, *, allow_hex: bool = False) -> int:
    try:
        stripped = value.strip()
        if allow_hex and stripped.lower().startswith("0x"):
            return int(stripped, 16)
        return int(stripped, 10)
    except (AttributeError, ValueError):
        raise ValueError(f"{label} must be an integer") from None


def _resolution(row: dict[str, str]) -> int | None:
    raw = row.get("actual_resolution_ns", "").strip()
    if not raw:
        return None
    value = _integer(raw, "actual_resolution_ns")
    if value <= 0:
        raise ValueError("actual_resolution_ns must be positive")
    return value


def _metadata(row: dict[str, str]) -> dict[str, str]:
    return {key: value for key, value in row.items() if key not in {"event_id", "format", "raw_value"}}


def _exfat(row: dict[str, str], resolution: int | None) -> DecodedTimestamp:
    match = re.fullmatch(r"\s*(0[xX][0-9a-fA-F]+|[0-9]+)\s*:\s*(0[xX][0-9a-fA-F]+|[0-9]+)\s*", row["raw_value"])
    if not match:
        raise ValueError("exFAT raw_value must be date_word:time_word")
    date_word = _integer(match.group(1), "exFAT date word", allow_hex=True)
    time_word = _integer(match.group(2), "exFAT time word", allow_hex=True)
    if not 0 <= date_word <= 0xffff or not 0 <= time_word <= 0xffff:
        raise ValueError("exFAT date and time words must be unsigned 16-bit values")
    year, month, day = 1980 + (date_word >> 9), (date_word >> 5) & 0xf, date_word & 0x1f
    hour, minute, two_seconds = (time_word >> 11) & 0x1f, (time_word >> 5) & 0x3f, time_word & 0x1f
    if two_seconds > 29:
        raise ValueError("exFAT seconds field must be between 0 and 29")
    kind = row.get("timestamp_kind", "").strip().lower()
    if kind not in {"creation", "modification", "access"}:
        raise ValueError("exFAT timestamp_kind must be creation, modification, or access")
    increment = row.get("increment", "").strip()
    if kind == "access":
        if increment:
            raise ValueError("exFAT access timestamps do not have an increment field")
        subsecond_ns, storage_ns = 0, 2_000_000_000
    else:
        if not increment:
            raise ValueError("exFAT creation/modification timestamps require increment 0..199")
        increment_value = _integer(increment, "exFAT increment")
        if not 0 <= increment_value <= 199:
            raise ValueError("exFAT increment must be between 0 and 199")
        subsecond_ns, storage_ns = increment_value * 10_000_000, 10_000_000
    try:
        local = datetime(year, month, day, hour, minute, two_seconds * 2, tzinfo=timezone.utc)
    except ValueError as error:
        raise ValueError(f"invalid exFAT calendar value: {error}") from None
    offset_byte_raw = row.get("utc_offset_byte", "").strip()
    if not offset_byte_raw:
        raise ValueError("exFAT utc_offset_byte is required")
    offset_byte = _integer(offset_byte_raw, "exFAT UTC offset byte", allow_hex=True)
    if not 0 <= offset_byte <= 0xff:
        raise ValueError("exFAT UTC offset byte must be in 0..255")
    offset_valid = bool(offset_byte & 0x80)
    if offset_valid:
        offset_units = offset_byte & 0x7f
        if offset_units & 0x40:
            offset_units -= 0x80
        offset_minutes = offset_units * 15
    else:
        declared_offset = row.get("utc_offset_minutes", "").strip()
        if not declared_offset:
            raise ValueError("exFAT UTC offset is invalid; provide utc_offset_minutes")
        offset_minutes = _integer(declared_offset, "utc_offset_minutes")
        if not -960 <= offset_minutes <= 945:
            raise ValueError("utc_offset_minutes must be between -960 and 945")
    if not -960 <= offset_minutes <= 945:
        raise ValueError("exFAT UTC offset byte is outside the supported range")
    delta = local.replace(tzinfo=None) - datetime(1970, 1, 1)
    utc_seconds = delta.days * 86_400 + delta.seconds - offset_minutes * 60
    point_ns = utc_seconds * 1_000_000_000 + subsecond_ns
    return DecodedTimestamp(row["event_id"], "exfat", row["raw_value"], point_ns, storage_ns, resolution, _metadata(row))


def decode_timestamp(row: dict[str, str]) -> DecodedTimestamp:
    """Decode one CSV-style row or raise ValueError with a reviewable reason."""
    for required in ("event_id", "format", "raw_value"):
        value = row.get(required)
        if value is None or not str(value).strip():
            raise ValueError(f"{required} is required")
    fmt = row["format"].strip().lower().replace("-", "").replace("_", "")
    raw = row["raw_value"].strip()
    resolution = _resolution(row)
    if fmt in {"apfs", "apfstime"}:
        point = _integer(raw, "APFS nanosecond timestamp")
        if not INT64_MIN <= point <= INT64_MAX:
            raise ValueError("APFS timestamp must be a signed 64-bit nanosecond value")
        try:
            from dfdatetime.apfs_time import APFSTime
            APFSTime(timestamp=point)
        except ImportError as error:
            raise ImportError(
                "APFS decoding requires dfDateTime; install VERITY's dependencies with `python -m pip install .`"
            ) from error
        return DecodedTimestamp(row["event_id"], "apfs", raw, point, 1, resolution, _metadata(row))
    if fmt in {"filetime", "ntfsfiletime", "ntfs"}:
        value = _integer(raw, "FILETIME value")
        if not 0 <= value <= UINT64_MAX:
            raise ValueError("FILETIME must be an unsigned 64-bit value")
        if value == 0:
            raise ValueError("FILETIME zero sentinel means the timestamp is not set")
        kind = row.get("timestamp_kind", "").strip().lower()
        if value == 0xffffffff and kind in {"access", "last_access_time"}:
            raise ValueError("FILETIME 0xffffffff sentinel means preserve the previous access time")
        # Construct dfDateTime values when installed, while keeping all conversions exact here.
        try:
            from dfdatetime.filetime import Filetime
            Filetime(timestamp=value)
        except ImportError as error:
            raise ImportError(
                "FILETIME decoding requires dfDateTime; install VERITY's dependencies with `python -m pip install .`"
            ) from error
        point = (value - FILETIME_EPOCH_DELTA) * 100
        return DecodedTimestamp(row["event_id"], "filetime", raw, point, 100, resolution, _metadata(row))
    if fmt == "exfat":
        return _exfat(row, resolution)
    if fmt in {"snowflake", "discordsnowflake", "discord"}:
        value = _integer(raw, "Discord Snowflake ID")
        if not 0 <= value <= UINT64_MAX:
            raise ValueError("Discord Snowflake ID must be an unsigned 64-bit value")
        timestamp_ms = (value >> 22) + SNOWFLAKE_EPOCH_MS
        point = timestamp_ms * NANOSECONDS_PER_MILLISECOND
        return DecodedTimestamp(row["event_id"], "snowflake", raw, point, NANOSECONDS_PER_MILLISECOND, resolution, _metadata(row))
    raise ValueError(f"unsupported timestamp format: {row['format']}")
