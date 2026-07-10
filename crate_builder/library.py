"""Scan a local music folder and build a searchable track index."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from mutagen import File as MutagenFile

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
