"""Scan a local music folder and build a searchable track index."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from mutagen import File as MutagenFile

from crate_builder.serato_database import SeratoDbTrack

AUDIO_EXTENSIONS = {".mp3", ".m4a", ".flac", ".wav", ".aiff", ".aif", ".ogg", ".alac"}

# Matches common "Artist - Title" style filenames, optionally with a leading
# track number like "03 - Artist - Title" or "03. Artist - Title".
_FILENAME_PATTERN = re.compile(
    r"^(?:\d+[\.\-\)]?\s*)?(?P<artist>.+?)\s*-\s*(?P<title>.+)$"
)


@dataclass
class Track:
    path: str
    title: str
    artist: str
    album: str = ""
    search_key: str = field(default="", repr=False)

    def __post_init__(self) -> None:
        self.search_key = f"{self.artist} {self.title}".strip().lower()


def _read_tags(path: str) -> tuple[str, str, str]:
    """Best-effort tag read. Returns (title, artist, album), any of which may be ''."""
    title = artist = album = ""
    try:
        audio = MutagenFile(path, easy=True)
    except Exception:
        audio = None

    if audio and audio.tags:
        title = (audio.tags.get("title") or [""])[0]
        artist = (audio.tags.get("artist") or [""])[0]
        album = (audio.tags.get("album") or [""])[0]

    if not title or not artist:
        fallback_title, fallback_artist = _parse_filename(path)
        title = title or fallback_title
        artist = artist or fallback_artist

    return title.strip(), artist.strip(), album.strip()


def _parse_filename(path: str) -> tuple[str, str]:
    stem = os.path.splitext(os.path.basename(path))[0]
    match = _FILENAME_PATTERN.match(stem)
    if match:
        return match.group("title").strip(), match.group("artist").strip()
    return stem.strip(), ""


def _path_key(path: str) -> str:
    return os.path.normcase(os.path.normpath(path))


def apply_serato_metadata(tracks: list[Track], serato_tracks: list[SeratoDbTrack]) -> list[Track]:
    """Overlay Serato's own database metadata onto scanned tracks, keyed by
    file path. Serato's title/artist/album is usually more accurate than raw
    file tags or a filename guess — it's what the DJ actually sees and edits
    in Serato, which may never get written back to the file itself. Only
    overwrites a field when Serato has a non-empty value for it; a track
    Serato doesn't know about yet (or with a field it also left blank) keeps
    what the plain filesystem scan found. Mutates and returns `tracks`."""
    by_path = {_path_key(t.path): t for t in serato_tracks if t.path}
    for track in tracks:
        serato_track = by_path.get(_path_key(track.path))
        if not serato_track:
            continue
        if serato_track.title:
            track.title = serato_track.title
        if serato_track.artist:
            track.artist = serato_track.artist
        if serato_track.album:
            track.album = serato_track.album
        track.search_key = f"{track.artist} {track.title}".strip().lower()
    return tracks


def scan_library(root_dir: str) -> list[Track]:
    """Recursively walk root_dir and return a Track for every audio file found."""
    if not os.path.isdir(root_dir):
        raise NotADirectoryError(f"Library folder not found: {root_dir}")

    tracks: list[Track] = []
    for dirpath, _dirnames, filenames in os.walk(root_dir):
        for filename in filenames:
            ext = os.path.splitext(filename)[1].lower()
            if ext not in AUDIO_EXTENSIONS:
                continue
            full_path = os.path.join(dirpath, filename)
            title, artist, album = _read_tags(full_path)
            if not title:
                title = os.path.splitext(filename)[0]
            tracks.append(Track(path=full_path, title=title, artist=artist, album=album))

    return tracks
