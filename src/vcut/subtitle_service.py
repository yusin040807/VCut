from __future__ import annotations

import re
from pathlib import Path

from .exceptions import SubtitleFormatError
from .models import SubtitleEntry
from .timecode import format_timecode, parse_srt_timecode, validate_range

_TIMING = re.compile(r"^\s*(.*?)\s*-->\s*(.*?)\s*$")


def parse_srt(text: str) -> list[SubtitleEntry]:
    normalized = text.replace("\r\n", "\n").strip()
    if not normalized:
        return []
    entries: list[SubtitleEntry] = []
    for number, block in enumerate(re.split(r"\n\s*\n", normalized), 1):
        lines = block.splitlines()
        if lines and lines[0].strip().isdigit():
            lines = lines[1:]
        if len(lines) < 2:
            raise SubtitleFormatError(f"Subtitle block {number} is incomplete.")
        match = _TIMING.match(lines[0])
        if not match:
            raise SubtitleFormatError(f"Subtitle block {number} has an invalid timestamp line.")
        try:
            start, end = map(parse_srt_timecode, match.groups())
            validate_range(start, end)
        except ValueError as exc:
            raise SubtitleFormatError(f"Subtitle block {number}: {exc}") from exc
        body = "\n".join(lines[1:]).strip()
        if not body:
            raise SubtitleFormatError(f"Subtitle block {number} has no text.")
        entries.append(SubtitleEntry(start, end, body, "SRT"))
    return entries


def import_srt(path: Path) -> list[SubtitleEntry]:
    try:
        return parse_srt(path.read_text(encoding="utf-8-sig"))
    except UnicodeDecodeError as exc:
        raise SubtitleFormatError("Subtitle file must use UTF-8 encoding.") from exc


def overlap_warnings(entries: list[SubtitleEntry]) -> list[str]:
    ordered = sorted(entries, key=lambda item: item.start)
    return [f"Subtitle {index} overlaps subtitle {index + 1}." for index, (left, right) in enumerate(zip(ordered, ordered[1:]), 1) if left.end > right.start]


def export_srt(entries: list[SubtitleEntry]) -> str:
    blocks = []
    for index, entry in enumerate(sorted(entries, key=lambda item: item.start), 1):
        blocks.append(f"{index}\n{format_timecode(entry.start, srt=True)} --> {format_timecode(entry.end, srt=True)}\n{entry.text}")
    return "\n\n".join(blocks) + ("\n" if blocks else "")
