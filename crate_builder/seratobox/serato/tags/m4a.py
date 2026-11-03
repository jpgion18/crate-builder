"""M4A/MP4: Serato data in freeform atoms, base64-wrapped in a GEOB-style envelope.

Atoms: `----:com.serato.dj:markersv2`, `----:com.serato.dj:beatgrid`.
"""

from __future__ import annotations

from pathlib import Path

from mutagen.mp4 import MP4

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

MARKERS2_ATOM = "----:com.serato.dj:markersv2"
BEATGRID_ATOM = "----:com.serato.dj:beatgrid"


def read_m4a(path: Path) -> TrackTags:
    tags = TrackTags()
    audio = MP4(path)
    fill_stream_info(tags, audio.info)
    atoms = audio.tags
    if atoms is None:
        return tags
    for atom, desc, apply in (
        (MARKERS2_ATOM, MARKERS2, apply_markers2),
        (BEATGRID_ATOM, BEATGRID, apply_beatgrid),
    ):
        values = atoms.get(atom)
        if not values:
            continue
        try:
            apply(tags, unwrap_envelope(bytes(values[0]), desc), f"M4A {atom}")
        except MarkersError as exc:
            tags.warnings.append(f"Malformed {desc} (M4A {atom}): {exc}")
    tags.title = first_text(atoms.get("\xa9nam"))
    tags.artist = first_text(atoms.get("\xa9ART"))
    tags.album = first_text(atoms.get("\xa9alb"))
    tags.genre = first_text(atoms.get("\xa9gen"))
    return tags
