from __future__ import annotations

import csv
from pathlib import Path

from .exceptions import ProgrammeFormatError
from .models import ProgrammeSegment
from .timecode import parse_timecode, validate_range

REQUIRED_COLUMNS = {"segment_id", "start_time", "end_time", "event_type", "description"}


def read_programme(path: Path) -> list[ProgrammeSegment]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
            if missing:
                raise ProgrammeFormatError(f"Missing CSV columns: {', '.join(sorted(missing))}")
            segments: list[ProgrammeSegment] = []
            seen: set[str] = set()
            for row_number, row in enumerate(reader, 2):
                try:
                    segment_id = row["segment_id"].strip()
                    if not segment_id or segment_id in seen:
                        raise ValueError("segment_id must be present and unique")
                    start = parse_timecode(row["start_time"])
                    end = parse_timecode(row["end_time"])
                    validate_range(start, end)
                    event_type = row["event_type"].strip().lower()
                    if not event_type:
                        raise ValueError("event_type is required")
                    seen.add(segment_id)
                    segments.append(ProgrammeSegment(segment_id, start, end, event_type, row["description"].strip()))
                except (KeyError, ValueError) as exc:
                    raise ProgrammeFormatError(f"Programme row {row_number}: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise ProgrammeFormatError("Programme CSV must use UTF-8 encoding.") from exc
    segments.sort(key=lambda item: (item.start, item.id))
    return segments
