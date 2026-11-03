"""Decode the `Serato BeatGrid` payload.

    01 00                          version
    u32 BE                         marker count
    markers:
      non-terminal: f32 position_s | u32 beats_to_next
      terminal:     f32 position_s | f32 bpm
    1 footer byte

Positions are already in seconds.
"""

from __future__ import annotations

import struct

from .models import GridMarker

VERSION = b"\x01\x00"


class BeatGridError(ValueError):
    pass


def decode_beatgrid(raw: bytes) -> list[GridMarker]:
    if raw[:2] != VERSION:
        raise BeatGridError(f"unexpected BeatGrid version {raw[:2].hex()}")
    if len(raw) < 6:
        raise BeatGridError("BeatGrid truncated before marker count")
    (count,) = struct.unpack(">I", raw[2:6])
    if len(raw) < 6 + count * 8:
        raise BeatGridError(f"BeatGrid declares {count} markers but is only {len(raw)} bytes")
    markers: list[GridMarker] = []
    pos = 6
    for i in range(count):
        chunk = raw[pos : pos + 8]
        pos += 8
        if i == count - 1:
            position, bpm = struct.unpack(">ff", chunk)
            markers.append(GridMarker(position_s=position, bpm=bpm))
        else:
            position, beats = struct.unpack(">fI", chunk)
            markers.append(GridMarker(position_s=position, beats_to_next=beats))
    return markers


def segment_bpm(markers: list[GridMarker], i: int) -> float | None:
    """BPM of the segment starting at marker `i`."""
    marker = markers[i]
    if marker.bpm is not None:
        return marker.bpm
    if marker.beats_to_next is None or i + 1 >= len(markers):
        return None
    span = markers[i + 1].position_s - marker.position_s
    if span <= 0:
        return None
    return marker.beats_to_next * 60.0 / span
