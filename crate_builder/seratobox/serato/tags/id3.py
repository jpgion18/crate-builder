"""Serato data in ID3 GEOB frames. Shared by MP3 and AIFF (AIFF keeps ID3 in an `ID3 ` chunk)."""

from __future__ import annotations

from ..models import TrackTags
from .common import BEATGRID, MARKERS2, apply_beatgrid, apply_markers2, first_text


def read_id3(tags: TrackTags, id3: object | None, where: str) -> None:
    if id3 is None:
        return
    getall = getattr(id3, "getall", None)
    if getall is None:
        return
    for frame in getall("GEOB"):
        if frame.desc == MARKERS2:
            apply_markers2(tags, bytes(frame.data), where)
        elif frame.desc == BEATGRID:
            apply_beatgrid(tags, bytes(frame.data), where)
    tags.title = first_text(_text(id3, "TIT2"))
    tags.artist = first_text(_text(id3, "TPE1"))
    tags.album = first_text(_text(id3, "TALB"))
    tags.genre = first_text(_text(id3, "TCON"))


def _text(id3: object, frame_id: str) -> list[str] | None:
    frame = getattr(id3, "get", lambda _k: None)(frame_id)
    return list(frame.text) if frame is not None else None
