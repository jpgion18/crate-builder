"""Plain data types produced by the Serato reader. No Rekordbox knowledge here."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Color:
    r: int
    g: int
    b: int

    @classmethod
    def from_bytes(cls, data: bytes) -> Color:
        return cls(data[0], data[1], data[2])

    def hex(self) -> str:
        return f"#{self.r:02X}{self.g:02X}{self.b:02X}"


@dataclass(frozen=True)
class Cue:
    """A Serato hot cue. `index` is Serato's slot (0 = A)."""

    index: int
    position_ms: int
    color: Color | None = None
    name: str = ""


@dataclass(frozen=True)
class Loop:
    """A Serato saved loop. `index` is Serato's loop slot (0-based)."""

    index: int
    start_ms: int
    end_ms: int
    color: Color | None = None
    name: str = ""
    locked: bool = False


@dataclass(frozen=True)
class GridMarker:
    """One Serato beatgrid marker.

    Non-terminal markers carry `beats_to_next`; the terminal marker carries `bpm`.
    """

    position_s: float
    beats_to_next: int | None = None
    bpm: float | None = None


@dataclass
class Markers:
    cues: list[Cue] = field(default_factory=list)
    loops: list[Loop] = field(default_factory=list)
    track_color: Color | None = None
    bpm_lock: bool | None = None


@dataclass
class Mp3Framing:
    """What we could learn about an MP3's first frame and gapless info."""

    has_xing: bool = False  # Xing or Info header frame present
    has_lame: bool = False  # LAME extension present in that frame
    encoder_delay: int | None = None  # samples, from the LAME tag
    padding: int | None = None  # samples, from the LAME tag
    sample_rate: int | None = None


@dataclass
class TrackTags:
    """Everything read from one audio file's tags."""

    markers: Markers | None = None
    beatgrid: list[GridMarker] | None = None
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    genre: str | None = None
    duration_s: float | None = None
    bitrate_kbps: int | None = None
    sample_rate: int | None = None
    mp3_framing: Mp3Framing | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class DatabaseTrack:
    """A track record from `database V2`."""

    path: str
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    genre: str | None = None
    bpm: str | None = None
    key: str | None = None
    comment: str | None = None
    date_added: int | None = None  # unix seconds


@dataclass
class Crate:
    """A crate. `parts` is the nesting path, e.g. ("House", "Deep")."""

    parts: tuple[str, ...]
    track_paths: list[str]
    file: Path | None = None

    @property
    def name(self) -> str:
        return self.parts[-1]
