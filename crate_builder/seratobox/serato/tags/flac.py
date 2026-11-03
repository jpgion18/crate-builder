"""FLAC: Serato data in Vorbis comments, base64-wrapped in a GEOB-style envelope.

Fields: `SERATO_MARKERS_V2`, `SERATO_BEATGRID`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mutagen.flac import FLAC

from ..markers2 import MarkersError
from ..models import TrackTags
from .common import (
    BEATGRID,
    MARKERS2,
    apply_beatgrid,
    apply_markers2,
    fill_stream_info,
    first_text,
    unwrap_envelope,
)

MARKERS2_FIELD = "SERATO_MARKERS_V2"
BEATGRID_FIELD = "SERATO_BEATGRID"


def read_flac(path: Path) -> TrackTags:
    tags = TrackTags()
    audio = FLAC(path)
    fill_stream_info(tags, audio.info)
    comments: Any = audio.tags  # VCFLACDict; mutagen types it as a union
    if comments is None:
        return tags
    for field, desc, apply in (
        (MARKERS2_FIELD, MARKERS2, apply_markers2),
        (BEATGRID_FIELD, BEATGRID, apply_beatgrid),
    ):
        values = comments.get(field)
        if not values:
            continue
        try:
            apply(tags, unwrap_envelope(values[0], desc), f"FLAC {field}")
        except MarkersError as exc:
            tags.warnings.append(f"Malformed {desc} (FLAC {field}): {exc}")
    tags.title = first_text(comments.get("title"))
    tags.artist = first_text(comments.get("artist"))
    tags.album = first_text(comments.get("album"))
    tags.genre = first_text(comments.get("genre"))
    return tags
