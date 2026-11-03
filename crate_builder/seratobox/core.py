"""`convert()`: Serato crates or tracks in, Rekordbox XML (or a dry-run report) out.

Read-only on the Serato library and audio files. The only file ever written is
`output_path`, and never in dry-run mode.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import mp3_offset
from .options import ConvertOptions, CueMode
from .rekordbox.validate import validate_tree
from .rekordbox.xml_writer import (
    HOT_CUE_SLOTS,
    MARK_LOOP,
    MEMORY_NUM,
    RbMark,
    RbNode,
    RbTempo,
    RbTrack,
    build_tree,
    write_xml,
)
from .report import Report, TrackReport
from .serato.beatgrid import segment_bpm
from .serato.crates import read_all_crates, select_crates
from .serato.database import read_database
from .serato.models import Crate, DatabaseTrack, GridMarker, Markers, TrackTags
from .serato.paths import candidate_paths, drive_root_for, resolve_track_path
from .serato.tags import READERS, format_of, read_tags

DIRECT_TRACKS_PLAYLIST = "Tracks"

ProgressCallback = Callable[[int, int, str], None]


class ConvertError(Exception):
    """Bad arguments or an unusable Serato folder. Per-track problems are warnings instead."""


@dataclass
class _Entry:
    stored: str
    resolved: Path | None = None
    crates: list[str] = field(default_factory=list)


def convert(
    sources: Sequence[str | Path],
    serato_dir: str | Path,
    output_path: str | Path | None,
    options: ConvertOptions | None = None,
    progress: ProgressCallback | None = None,
) -> Report:
    """Convert Serato crates and/or individual tracks to a Rekordbox XML file.

    `sources` holds crate names (`House`, `House%%Deep` or `House/Deep`) and/or
    paths to audio files. With `options.dry_run` everything is parsed and
    reported but nothing is written, and `output_path` may be None.

    `progress(done, total, label)` is called before each track is read, and
    once more with done == total at the end.
    """
    options = options or ConvertOptions()
    serato = Path(serato_dir).expanduser()
    if not serato.is_dir():
        raise ConvertError(f"Serato folder not found: {serato}")
    output = Path(output_path).expanduser() if output_path is not None else None
    if output is None and not options.dry_run:
        raise ConvertError("output_path is required unless dry_run is set")
    if output is not None:
        _check_output_safe(output, serato)
    offset_mode, fixed_ms = options.mp3_offset_mode()

    report = Report(
        serato_dir=str(serato),
        output_path=str(output) if output else None,
        cue_mode=CueMode(options.cue_mode).value,
    )

    crate_names, track_files = _split_sources(sources)
    selected: list[Crate] = []
    if options.all_crates or crate_names:
        crates = read_all_crates(serato, report.warnings)
        if options.all_crates:
            selected = sorted(crates, key=lambda c: c.parts)
        else:
            selected, missing = select_crates(crates, crate_names, options.include_subcrates)
            for name in missing:
                report.warnings.append(f"Crate not found: {name}")
    if not selected and not track_files:
        raise ConvertError("Nothing to convert: no matching crates or track files")
    report.crates = [" > ".join(c.parts) for c in selected]

    entries = _collect_entries(selected, track_files, serato, options.path_roots)
    database = _index_database(read_database(serato, report.warnings), serato, options.path_roots)

    rb_tracks: list[RbTrack] = []
    ids_by_stored: dict[str, int] = {}
    total = len(entries)
    for done, entry in enumerate(entries.values()):
        if progress is not None:
            progress(done, total, Path(entry.stored).name)
        track_report = TrackReport(stored_path=entry.stored, crates=entry.crates)
        report.tracks.append(track_report)
        if entry.resolved is None:
            track_report.warnings.append("File not found; left out of the XML")
            continue
        track_report.resolved_path = str(entry.resolved)
        rb = _build_track(
            len(rb_tracks) + 1,
            entry.resolved,
            database.get(_nfc(entry.stored)) or database.get(_nfc(str(entry.resolved))),
            options,
            offset_mode,
            fixed_ms,
            track_report,
        )
        rb_tracks.append(rb)
        ids_by_stored[entry.stored] = rb.track_id

    nodes = _build_playlists(selected, ids_by_stored)
    direct = [ids_by_stored[s] for s in _direct_keys(track_files) if s in ids_by_stored]
    if direct:
        nodes.append(RbNode(DIRECT_TRACKS_PLAYLIST, track_ids=direct))

    if progress is not None:
        progress(total, total, "")
    problems = validate_tree(build_tree(rb_tracks, nodes).getroot())
    report.warnings.extend(f"XML check: {p}" for p in problems)

    if not options.dry_run and output is not None:
        write_xml(rb_tracks, nodes, output)
        report.written = True
    return report


def _check_output_safe(output: Path, serato: Path) -> None:
    resolved = output.resolve()
    if resolved.is_relative_to(serato.resolve()):
        raise ConvertError(f"Refusing to write inside the Serato folder: {output}")
    if resolved.suffix.lower() in READERS:
        raise ConvertError(f"Refusing to write to an audio file path: {output}")
    if resolved.is_dir():
        raise ConvertError(f"Output path is a directory: {output}")


def _split_sources(sources: Sequence[str | Path]) -> tuple[list[str], list[Path]]:
    names: list[str] = []
    files: list[Path] = []
    for source in sources:
        path = Path(source).expanduser()
        if isinstance(source, Path) or path.is_file() or path.suffix.lower() in READERS:
            files.append(path)
        else:
            names.append(str(source))
    return names, files


def _index_database(
    tracks: dict[str, DatabaseTrack], serato: Path, roots: list[Path]
) -> dict[str, DatabaseTrack]:
    """Key database entries by their stored path and by every place that path could be.

    Crates and the database can spell the same file differently: Crate Builder
    writes `Volumes/USB/Music/a.mp3` where a database on that drive says
    `Music/a.mp3`. Matching on the possible full paths (string work only, no
    disk access) finds the entry either way.
    """
    index: dict[str, DatabaseTrack] = {}
    for stored, track in tracks.items():
        index.setdefault(_nfc(stored), track)
        for candidate in candidate_paths(stored, serato, roots):
            index.setdefault(_nfc(str(candidate)), track)
    return index


def _nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def _stored_for_file(path: Path) -> str:
    absolute = path.resolve() if path.exists() else path.absolute()
    return absolute.relative_to(drive_root_for(absolute)).as_posix()


def _direct_keys(files: list[Path]) -> list[str]:
    return [_stored_for_file(f) for f in files]


def _collect_entries(
    crates: list[Crate], files: list[Path], serato: Path, roots: list[Path]
) -> dict[str, _Entry]:
    entries: dict[str, _Entry] = {}
    for crate in crates:
        label = " > ".join(crate.parts)
        for stored in crate.track_paths:
            entry = entries.get(stored)
            if entry is None:
                entry = entries[stored] = _Entry(stored, resolve_track_path(stored, serato, roots))
            if label not in entry.crates:
                entry.crates.append(label)
    for path in files:
        stored = _stored_for_file(path)
        if stored not in entries:
            entries[stored] = _Entry(stored, path if path.is_file() else None)
    return entries


def _build_track(
    track_id: int,
    path: Path,
    db: DatabaseTrack | None,
    options: ConvertOptions,
    offset_mode: str,
    fixed_ms: float,
    report: TrackReport,
) -> RbTrack:
    fmt = format_of(path)
    tags: TrackTags = read_tags(path)
    report.format = fmt
    report.warnings.extend(tags.warnings)

    offset_ms = 0.0
    if fmt == "MP3":
        report.mp3_framing = mp3_offset.describe(tags.mp3_framing)
        offset_ms = mp3_offset.offset_ms(offset_mode, fixed_ms, tags.mp3_framing)
    report.offset_ms = offset_ms
    offset_s = offset_ms / 1000.0

    title = (db.title if db else None) or tags.title or path.stem
    artist = (db.artist if db else None) or tags.artist or ""
    report.title, report.artist = title, artist

    tempos, grid_bpm = _build_tempo(tags.beatgrid, offset_s, report)
    marks = _build_marks(tags.markers, CueMode(options.cue_mode), offset_s, report)
    if tags.markers is None and not any("Markers2" in w for w in report.warnings):
        report.warnings.append("No Serato cues or loops")

    bpm = grid_bpm or _parse_bpm(db.bpm if db else None)
    report.bpm = bpm
    return RbTrack(
        track_id=track_id,
        path=path,
        name=title,
        artist=artist,
        album=(db.album if db else None) or tags.album or "",
        genre=(db.genre if db else None) or tags.genre or "",
        kind=f"{fmt} File" if fmt else "",
        size=path.stat().st_size,
        total_time_s=tags.duration_s,
        average_bpm=bpm,
        date_added=_date(db.date_added if db else None),
        bit_rate=tags.bitrate_kbps,
        sample_rate=tags.sample_rate,
        comments=(db.comment if db else None) or "",
        tonality=(db.key if db else None) or "",
        tempos=tempos,
        marks=marks,
    )


def _build_tempo(
    grid: list[GridMarker] | None, offset_s: float, report: TrackReport
) -> tuple[list[RbTempo], float | None]:
    if not grid:
        report.warnings.append("No Serato beatgrid")
        return [], None
    report.grid_markers = len(grid)
    bpm = segment_bpm(grid, 0)
    if bpm is None or not 1 <= bpm <= 999:
        report.warnings.append(f"Beatgrid has unusable BPM {bpm}; grid skipped")
        return [], None
    if len(grid) > 1:
        report.warnings.append(
            f"Variable beatgrid ({len(grid)} markers) flattened to the first marker, {bpm:.2f} BPM"
        )
    inizio = grid[0].position_s + offset_s
    beat = 60.0 / bpm
    while inizio < 0:  # first beat before the track start: move to the first beat inside it
        inizio += beat
    return [RbTempo(inizio_s=inizio, bpm=bpm)], bpm


def _build_marks(
    markers: Markers | None, mode: CueMode, offset_s: float, report: TrackReport
) -> list[RbMark]:
    if markers is None:
        return []
    marks: list[RbMark] = []
    want_hot = mode in (CueMode.HOTCUES, CueMode.BOTH)
    want_memory = mode in (CueMode.MEMORY, CueMode.BOTH)

    def at(ms: int, what: str) -> float:
        position = ms / 1000.0 + offset_s
        if position < 0:
            report.warnings.append(f"{what} moved from {position:.3f}s to 0 by the MP3 offset")
            return 0.0
        return position

    used_slots: set[int] = set()
    for cue in markers.cues:
        label = f"Cue {_slot_letter(cue.index)}"
        start = at(cue.position_ms, label)
        rgb = (cue.color.r, cue.color.g, cue.color.b) if cue.color else None
        if want_hot:
            if cue.index < HOT_CUE_SLOTS:
                marks.append(RbMark(start_s=start, num=cue.index, name=cue.name, rgb=rgb))
                used_slots.add(cue.index)
                report.hot_cues += 1
            else:
                report.warnings.append(
                    f"Serato cue slot {cue.index + 1} has no Rekordbox hot cue slot (A-H)"
                    + ("; kept as memory cue" if want_memory else "; skipped")
                )
        if want_memory:
            marks.append(RbMark(start_s=start, num=MEMORY_NUM, name=cue.name))
            report.memory_cues += 1

    for loop in markers.loops:
        if loop.end_ms <= loop.start_ms:
            report.warnings.append(f"Loop {loop.index + 1} has end before start; skipped")
            continue
        label = f"Loop {loop.index + 1}"
        start, end = at(loop.start_ms, label), at(loop.end_ms, label)
        if want_memory:
            marks.append(
                RbMark(start_s=start, end_s=end, num=MEMORY_NUM, type=MARK_LOOP, name=loop.name)
            )
            report.loops += 1
        else:
            free = next((s for s in range(HOT_CUE_SLOTS) if s not in used_slots), None)
            if free is None:
                report.warnings.append(f"{label}: no free hot cue slot; skipped")
                continue
            used_slots.add(free)
            rgb = (loop.color.r, loop.color.g, loop.color.b) if loop.color else None
            marks.append(
                RbMark(start_s=start, end_s=end, num=free, type=MARK_LOOP, name=loop.name, rgb=rgb)
            )
            report.loops += 1
    return marks


def _build_playlists(crates: list[Crate], ids_by_stored: dict[str, int]) -> list[RbNode]:
    """Turn crates into Rekordbox nodes.

    Rekordbox nodes are either folders or playlists, while a Serato crate can
    have tracks and subcrates. Such a crate becomes a folder holding a playlist
    of its own tracks (same name) followed by its subcrates.
    """

    @dataclass
    class _Tree:
        name: str
        children: dict[str, _Tree] = field(default_factory=dict)
        crate: Crate | None = None

    root = _Tree("ROOT")
    for crate in crates:
        node = root
        for part in crate.parts:
            node = node.children.setdefault(part, _Tree(part))
        node.crate = crate

    def emit(tree: _Tree) -> RbNode:
        ids = _ids_for(tree.crate, ids_by_stored)
        if not tree.children:
            return RbNode(tree.name, track_ids=ids)
        children = [emit(child) for child in tree.children.values()]
        if tree.crate is not None and ids:
            children.insert(0, RbNode(tree.name, track_ids=ids))
        return RbNode(tree.name, children=children)

    return [emit(child) for child in root.children.values()]


def _ids_for(crate: Crate | None, ids_by_stored: dict[str, int]) -> list[int]:
    if crate is None:
        return []
    return [ids_by_stored[p] for p in crate.track_paths if p in ids_by_stored]


def _slot_letter(index: int) -> str:
    return chr(ord("A") + index) if 0 <= index < 26 else str(index + 1)


def _parse_bpm(text: str | None) -> float | None:
    try:
        value = float(text) if text else None
    except ValueError:
        return None
    return value if value and value > 0 else None


def _date(timestamp: int | None) -> str:
    if not timestamp:
        return ""
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d")
