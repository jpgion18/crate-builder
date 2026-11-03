"""Per-format readers for Serato data stored in audio file tags. All read-only."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ..models import TrackTags
from .aiff import read_aiff
from .flac import read_flac
from .m4a import read_m4a
from .mp3 import read_mp3

READERS: dict[str, Callable[[Path], TrackTags]] = {
    ".mp3": read_mp3,
    ".m4a": read_m4a,
    ".mp4": read_m4a,
    ".aac": read_m4a,
    ".flac": read_flac,
    ".aif": read_aiff,
    ".aiff": read_aiff,
}

FORMAT_NAMES = {
    ".mp3": "MP3",
    ".m4a": "M4A",
    ".mp4": "M4A",
    ".aac": "M4A",
    ".flac": "FLAC",
    ".aif": "AIFF",
    ".aiff": "AIFF",
}


def format_of(path: Path) -> str | None:
    return FORMAT_NAMES.get(path.suffix.lower())


def read_tags(path: Path) -> TrackTags:
    """Read Serato markers, beatgrid and basic metadata. Never raises for bad tags.

    Unsupported formats and unreadable files return a TrackTags with a warning.
    """
    reader = READERS.get(path.suffix.lower())
    if reader is None:
        return TrackTags(warnings=[f"Unsupported format {path.suffix or '(none)'}"])
    try:
        return reader(path)
    except Exception as exc:  # mutagen raises many types for corrupt files
        return TrackTags(warnings=[f"Could not read tags: {type(exc).__name__}: {exc}"])


__all__ = ["READERS", "format_of", "read_tags"]
