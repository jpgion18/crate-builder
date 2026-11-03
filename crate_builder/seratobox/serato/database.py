"""Read Serato's `_Serato_/database V2` for track metadata.

Each track is an `otrk` record; `pfil` is its path relative to the drive root.
"""

from __future__ import annotations

from pathlib import Path

from .models import DatabaseTrack
from .tlv import TLVError, decode_str, decode_u32, iter_records

DATABASE_FILE = "database V2"

_TEXT_FIELDS = {
    "tsng": "title",
    "tart": "artist",
    "talb": "album",
    "tgen": "genre",
    "tbpm": "bpm",
    "tkey": "key",
    "tcom": "comment",
}


def parse_database_bytes(data: bytes) -> list[DatabaseTrack]:
    tracks: list[DatabaseTrack] = []
    for tag, value in iter_records(data):
        if tag != "otrk":
            continue
        fields: dict[str, str | int | None] = {}
        path: str | None = None
        for sub_tag, sub_value in iter_records(value):
            if sub_tag == "pfil":
                path = decode_str(sub_value)
            elif sub_tag in _TEXT_FIELDS:
                fields[_TEXT_FIELDS[sub_tag]] = decode_str(sub_value) or None
            elif sub_tag == "uadd":
                fields["date_added"] = decode_u32(sub_value)
        if path:
            tracks.append(DatabaseTrack(path=path, **fields))  # type: ignore[arg-type]
    return tracks


def read_database(serato_dir: Path, warnings: list[str] | None = None) -> dict[str, DatabaseTrack]:
    """Return tracks keyed by their stored path. Missing or broken database yields {}."""
    path = serato_dir / DATABASE_FILE
    if not path.is_file():
        if warnings is not None:
            warnings.append(f"No '{DATABASE_FILE}' in {serato_dir}; using file tags only")
        return {}
    try:
        tracks = parse_database_bytes(path.read_bytes())
    except (OSError, TLVError) as exc:
        if warnings is None:
            raise
        warnings.append(f"Could not read '{DATABASE_FILE}': {exc}; using file tags only")
        return {}
    return {t.path: t for t in tracks}
