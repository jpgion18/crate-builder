"""Turn pasted text (CSV or plain track list) into a list of InputTrack rows."""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass

TITLE_HEADER_ALIASES = {
    "title",
    "track",
    "track name",
    "track title",
    "song",
    "song name",
    "song title",
    "name",
}
ARTIST_HEADER_ALIASES = {
    "artist",
    "artist name",
    "artist name(s)",
    "artist(s)",
    "artists",
    "performer",
}

# "Artist - Title", "Artist – Title" (en dash), "Artist — Title" (em dash)
_LINE_SPLIT_PATTERN = re.compile(r"\s+[-–—]\s+")


@dataclass
class InputTrack:
    artist: str
    title: str
    raw: str


def parse_input_text(text: str) -> list[InputTrack]:
    """Auto-detect CSV vs plain-text track list and parse accordingly."""
    text = text.strip()
    if not text:
        return []

    lines = [line for line in text.splitlines() if line.strip()]
    if _looks_like_csv(lines):
        return _parse_csv(text)
    return _parse_plain_text(lines)


def _looks_like_csv(lines: list[str]) -> bool:
    if len(lines) == 0:
        return False
    sample = lines[: min(5, len(lines))]
    comma_counts = [line.count(",") for line in sample]
    # CSV if every sampled line has at least one comma and the comma count
    # is consistent (a real delimiter, not incidental punctuation).
    return all(c > 0 for c in comma_counts) and len(set(comma_counts)) == 1


def _parse_csv(text: str) -> list[InputTrack]:
    reader = csv.reader(io.StringIO(text))
    rows = [row for row in reader if any(cell.strip() for cell in row)]
    if not rows:
        return []

    header = [cell.strip().lower() for cell in rows[0]]
    title_idx = next((i for i, h in enumerate(header) if h in TITLE_HEADER_ALIASES), None)
    artist_idx = next((i for i, h in enumerate(header) if h in ARTIST_HEADER_ALIASES), None)

    if title_idx is not None or artist_idx is not None:
        data_rows = rows[1:]
    else:
        # No recognizable header: assume the common "artist,title" layout.
        artist_idx, title_idx = 0, 1
        data_rows = rows

    results = []
    for row in data_rows:
        artist = row[artist_idx].strip() if artist_idx is not None and artist_idx < len(row) else ""
        title = row[title_idx].strip() if title_idx is not None and title_idx < len(row) else ""
        if not title and not artist:
            continue
        results.append(InputTrack(artist=artist, title=title, raw=",".join(row)))
    return results


def _parse_plain_text(lines: list[str]) -> list[InputTrack]:
    results = []
    for line in lines:
        line = line.strip().lstrip("0123456789.() \t")
        parts = _LINE_SPLIT_PATTERN.split(line, maxsplit=1)
        if len(parts) == 2:
            artist, title = parts[0].strip(), parts[1].strip()
        else:
            artist, title = "", line.strip()
        if title or artist:
            results.append(InputTrack(artist=artist, title=title, raw=line))
    return results
