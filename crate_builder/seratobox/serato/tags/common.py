"""Shared helpers for the per-format tag readers."""

from __future__ import annotations

from ..beatgrid import BeatGridError, decode_beatgrid
from ..markers2 import MarkersError, decode_markers2, lenient_b64decode
from ..models import TrackTags

MARKERS2 = "Serato Markers2"
BEATGRID = "Serato BeatGrid"


def unwrap_envelope(value: bytes | str, expected_desc: str) -> bytes:
    """Unwrap the base64 GEOB-style envelope used in M4A atoms and FLAC comments.

    Decoded, it is `mime NUL filename NUL description NUL data`. Returns `data`.
    """
    raw = value.encode("ascii", errors="ignore") if isinstance(value, str) else value
    decoded = lenient_b64decode(raw)
    parts = decoded.split(b"\x00", 3)
    if len(parts) != 4:
        raise MarkersError("envelope missing mime/filename/description header")
    desc = parts[2].decode("latin-1")
    if desc != expected_desc:
        raise MarkersError(f"envelope description is {desc!r}, expected {expected_desc!r}")
    return parts[3]


def apply_markers2(tags: TrackTags, raw: bytes, where: str) -> None:
    try:
        markers, warnings = decode_markers2(raw)
    except (MarkersError, IndexError) as exc:
        tags.warnings.append(f"Malformed {MARKERS2} ({where}): {exc}")
        return
    tags.markers = markers
    tags.warnings.extend(f"{w} ({where})" for w in warnings)


def apply_beatgrid(tags: TrackTags, raw: bytes, where: str) -> None:
    try:
        tags.beatgrid = decode_beatgrid(raw)
    except BeatGridError as exc:
        tags.warnings.append(f"Malformed {BEATGRID} ({where}): {exc}")


def first_text(value: object) -> str | None:
    if isinstance(value, list):
        value = value[0] if value else None
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def fill_stream_info(tags: TrackTags, info: object) -> None:
    length = getattr(info, "length", None)
    tags.duration_s = float(length) if length else None
    bitrate = getattr(info, "bitrate", None)
    tags.bitrate_kbps = int(bitrate) // 1000 if bitrate else None
    rate = getattr(info, "sample_rate", None)
    tags.sample_rate = int(rate) if rate else None
