"""Small immutable records used by the VERITY library."""

from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True)
class DecodedTimestamp:
    event_id: str
    format: str
    raw_value: str
    point_ns: int
    storage_granularity_ns: int
    actual_resolution_ns: int | None
    source_metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class TimestampInterval:
    start_ns: int
    end_ns: int

    def __post_init__(self) -> None:
        if self.start_ns > self.end_ns:
            raise ValueError("timestamp interval must not be empty")


@dataclass(frozen=True)
class ComparisonResult:
    first_precedes_second: bool
    second_precedes_first: bool
    explanation: str = ""
