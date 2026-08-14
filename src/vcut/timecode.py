from __future__ import annotations

import re

_TIMECODE = re.compile(r"^(?:(\d+):)?([0-5]?\d):([0-5]?\d)(?:[.,](\d{1,3}))?$")


def parse_timecode(value: str | float | int) -> float:
    if isinstance(value, (float, int)):
        if value < 0:
            raise ValueError("Time cannot be negative.")
        return float(value)
    text = value.strip()
    try:
        numeric = float(text)
    except ValueError:
        numeric = None
    if numeric is not None:
        if numeric < 0:
            raise ValueError("Time cannot be negative.")
        return numeric
    match = _TIMECODE.fullmatch(text)
    if not match:
        raise ValueError(f"Invalid timecode: {value}")
    hours, minutes, seconds, millis = match.groups()
    fraction = int((millis or "0").ljust(3, "0")) / 1000
    return int(hours or 0) * 3600 + int(minutes) * 60 + int(seconds) + fraction


def parse_srt_timecode(value: str) -> float:
    return parse_timecode(value.replace(",", "."))


def format_timecode(seconds: float, *, srt: bool = False) -> str:
    if seconds < 0:
        raise ValueError("Time cannot be negative.")
    total_ms = round(seconds * 1000)
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    separator = "," if srt else "."
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{separator}{millis:03d}"


def validate_range(start: float, end: float) -> None:
    if start < 0 or end <= start:
        raise ValueError("End time must be later than a non-negative start time.")
