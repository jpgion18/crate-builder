"""AIFF: Serato data in GEOB frames inside the `ID3 ` chunk, same as MP3."""

from __future__ import annotations

from pathlib import Path

from mutagen.aiff import AIFF

from ..models import TrackTags
from .common import fill_stream_info
from .id3 import read_id3


def read_aiff(path: Path) -> TrackTags:
    tags = TrackTags()
    audio = AIFF(path)
    fill_stream_info(tags, audio.info)
    read_id3(tags, audio.tags, "AIFF ID3 GEOB")
    return tags
