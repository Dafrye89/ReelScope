from __future__ import annotations

import re
from pathlib import Path


TIMING_RE = re.compile(
    r"^(?P<start>\d{2,}:\d{2}:\d{2}[,.]\d{3})\s+-->\s+(?P<end>\d{2,}:\d{2}:\d{2}[,.]\d{3})"
)


def timestamp_to_seconds(value: str) -> float:
    normalized = value.replace(".", ",")
    clock, milliseconds = normalized.split(",", 1)
    hours, minutes, seconds = (int(part) for part in clock.split(":"))
    return hours * 3600 + minutes * 60 + seconds + int(milliseconds[:3].ljust(3, "0")) / 1000


def seconds_to_timestamp(seconds: float) -> str:
    milliseconds = max(0, round(float(seconds) * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def read_srt(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    normalized = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []

    cues: list[dict] = []
    for block in re.split(r"\n{2,}", normalized):
        lines = block.split("\n")
        if len(lines) < 2:
            continue
        timing_index = 1 if lines[0].strip().isdigit() else 0
        match = TIMING_RE.match(lines[timing_index].strip())
        if match is None:
            continue
        text = "\n".join(lines[timing_index + 1 :]).strip()
        start = timestamp_to_seconds(match.group("start"))
        end = timestamp_to_seconds(match.group("end"))
        cues.append({"index": len(cues) + 1, "start": start, "end": max(start + 0.001, end), "text": text})
    return cues


def update_cue_text(cues: list[dict], updates: object) -> list[dict]:
    if not isinstance(updates, list) or len(updates) != len(cues):
        raise ValueError("the complete transcript cue list is required")
    updated: list[dict] = []
    for expected, incoming in zip(cues, updates, strict=True):
        if not isinstance(incoming, dict) or incoming.get("index") != expected["index"]:
            raise ValueError("transcript cue indexes do not match")
        text = incoming.get("text")
        if not isinstance(text, str):
            raise ValueError("each transcript cue must contain text")
        normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not normalized:
            raise ValueError("transcript cues cannot be empty")
        if len(normalized) > 2_000:
            raise ValueError("a transcript cue cannot exceed 2,000 characters")
        updated.append({**expected, "text": normalized})
    return updated


def write_srt(path: Path, cues: list[dict]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for position, cue in enumerate(cues, start=1):
            handle.write(
                f"{position}\n{seconds_to_timestamp(cue['start'])} --> {seconds_to_timestamp(cue['end'])}\n"
                f"{cue['text']}\n\n"
            )
    temporary.replace(path)
