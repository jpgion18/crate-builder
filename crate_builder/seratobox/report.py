"""The result of a conversion: what was found, what was written, what went wrong."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class TrackReport:
    stored_path: str
    resolved_path: str | None = None
    format: str | None = None
    title: str | None = None
    artist: str | None = None
    hot_cues: int = 0
    memory_cues: int = 0
    loops: int = 0
    bpm: float | None = None
    grid_markers: int = 0
    mp3_framing: str | None = None
    offset_ms: float = 0.0
    crates: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def found(self) -> bool:
        return self.resolved_path is not None


@dataclass
class Report:
    serato_dir: str
    output_path: str | None
    written: bool = False
    cue_mode: str = "both"
    crates: list[str] = field(default_factory=list)
    tracks: list[TrackReport] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def missing(self) -> list[TrackReport]:
        return [t for t in self.tracks if not t.found]

    @property
    def exported(self) -> list[TrackReport]:
        return [t for t in self.tracks if t.found]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for track, raw in zip(self.tracks, data["tracks"], strict=True):
            raw["found"] = track.found
        return data

    def render(self) -> str:
        lines: list[str] = []
        head = "Dry run, nothing written" if not self.written else f"Wrote {self.output_path}"
        lines.append(f"SeratoBox report: {head}")
        lines.append(f"Serato folder: {self.serato_dir}")
        lines.append(f"Cue mode:      {self.cue_mode}")
        lines.append(f"Crates ({len(self.crates)}): {', '.join(self.crates) or '(none)'}")
        exported = self.exported
        lines.append(
            f"Tracks: {len(self.tracks)} referenced, {len(exported)} exported, "
            f"{len(self.missing)} missing"
        )
        lines.append(
            f"Totals: {sum(t.hot_cues for t in exported)} hot cues, "
            f"{sum(t.memory_cues for t in exported)} memory cues, "
            f"{sum(t.loops for t in exported)} loops, "
            f"{sum(1 for t in exported if t.grid_markers)} tracks with beatgrids"
        )
        lines.append("")
        for t in self.tracks:
            label = " - ".join(p for p in (t.artist, t.title) if p) or Path(t.stored_path).name
            if not t.found:
                lines.append(f"  MISSING  {label}")
                lines.append(f"           {t.stored_path}")
            else:
                bpm = f"{t.bpm:.2f} BPM" if t.bpm else "no grid"
                lines.append(
                    f"  {t.format or '?':<5}    {label}  |  {t.hot_cues} hot, {t.memory_cues} mem, "
                    f"{t.loops} loops, {bpm}"
                )
                if t.mp3_framing:
                    shift = f", shift {t.offset_ms:+.1f} ms" if t.offset_ms else ""
                    lines.append(f"           MP3: {t.mp3_framing}{shift}")
            for w in t.warnings:
                lines.append(f"           ! {w}")
        if self.warnings:
            lines.append("")
            lines.append("Warnings:")
            lines.extend(f"  ! {w}" for w in self.warnings)
        return "\n".join(lines)
