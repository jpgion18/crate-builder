"""Conversion options. Plain data so a host app can build them without the CLI."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class CueMode(str, Enum):
    HOTCUES = "hotcues"  # Serato cues -> Rekordbox hot cues only
    MEMORY = "memory"  # Serato cues -> Rekordbox memory cues only
    BOTH = "both"  # each Serato cue -> a hot cue and a memory cue at the same spot


@dataclass
class ConvertOptions:
    cue_mode: CueMode = CueMode.BOTH
    dry_run: bool = False
    # "auto", "off", or a number of milliseconds to add to every MP3 position.
    mp3_offset: str | float = "auto"
    # Selecting a crate also selects the crates nested under it.
    include_subcrates: bool = True
    # Convert every crate in Subcrates (ignores crate names in `sources`).
    all_crates: bool = False
    # Extra drive roots to try when resolving Serato's stored paths.
    path_roots: list[Path] = field(default_factory=list)

    def mp3_offset_mode(self) -> tuple[str, float]:
        """Return ("auto" | "off" | "fixed", ms)."""
        value = self.mp3_offset
        if isinstance(value, (int, float)):
            return "fixed", float(value)
        text = str(value).strip().lower()
        if text in ("auto", "off"):
            return text, 0.0
        try:
            return "fixed", float(text)
        except ValueError as exc:
            raise ValueError(
                f"mp3_offset must be 'auto', 'off' or a number, not {value!r}"
            ) from exc
