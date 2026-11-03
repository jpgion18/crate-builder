"""Decode the `Serato Markers2` payload: hot cues, saved loops, colors and names.

Layout (after unwrapping the container-specific envelope, see `tags/`):

    01 01                          version
    base64 text, wrapped at 72 chars with `\\n`, NUL-terminated, then NUL padding

The base64 decodes to:

    01 01                          version
    entries, each: name (ASCII, NUL-terminated) | u32 BE length | data
    00                             end

Entries we read:

    COLOR    00 | rgb(3)                                          track color
    CUE      00 | index | pos_ms u32 | 00 | rgb(3) | 00 00 | name NUL
    LOOP     00 | index | start_ms u32 | end_ms u32 | ff ff ff ff
             | 00 | rgb(3) | 00 | locked | name NUL
    BPMLOCK  locked(1)

Unknown entries (e.g. FLIP) are skipped.
"""

from __future__ import annotations

import base64
import binascii
import struct

from .models import Color, Cue, Loop, Markers

VERSION = b"\x01\x01"


class MarkersError(ValueError):
    pass


def lenient_b64decode(text: bytes) -> bytes:
    """Decode Serato's base64: line-wrapped, often without `=` padding.

    A leftover single character (length % 4 == 1) carries no full byte; Serato
    writes these and other readers pad them with `A==`, which we mirror.
    """
    data = b"".join(text.split())
    remainder = len(data) % 4
    if remainder == 1:
        data += b"A=="
    elif remainder:
        data += b"=" * (4 - remainder)
    try:
        return base64.b64decode(data)
    except binascii.Error as exc:
        raise MarkersError(f"invalid base64: {exc}") from exc


def decode_markers2(raw: bytes) -> tuple[Markers, list[str]]:
    """Decode a Markers2 blob (starting with `01 01` + base64). Returns markers and warnings."""
    if raw[:2] != VERSION:
        raise MarkersError(f"unexpected Markers2 version {raw[:2].hex()}")
    body = raw[2:]
    nul = body.find(b"\x00")
    if nul != -1:
        body = body[:nul]
    payload = lenient_b64decode(body)
    return parse_markers2_payload(payload)


def parse_markers2_payload(payload: bytes) -> tuple[Markers, list[str]]:
    if payload[:2] != VERSION:
        raise MarkersError(f"unexpected Markers2 payload version {payload[:2].hex()}")
    markers = Markers()
    warnings: list[str] = []
    pos = 2
    end = len(payload)
    while pos < end:
        nul = payload.find(b"\x00", pos)
        if nul == -1:
            warnings.append("Markers2 data ends mid-entry")
            break
        name = payload[pos:nul].decode("ascii", errors="replace")
        pos = nul + 1
        if not name:  # terminating NUL
            break
        if pos + 4 > end:
            warnings.append(f"Markers2 entry {name} truncated")
            break
        (length,) = struct.unpack(">I", payload[pos : pos + 4])
        pos += 4
        data = payload[pos : pos + length]
        pos += length
        if len(data) < length:
            warnings.append(f"Markers2 entry {name} truncated")
            break
        try:
            if name == "CUE":
                markers.cues.append(_parse_cue(data))
            elif name == "LOOP":
                markers.loops.append(_parse_loop(data))
            elif name == "COLOR":
                markers.track_color = Color.from_bytes(data[1:4])
            elif name == "BPMLOCK":
                markers.bpm_lock = bool(data[0]) if data else None
        except (struct.error, IndexError) as exc:
            warnings.append(f"Skipped malformed Markers2 {name} entry: {exc}")
    markers.cues.sort(key=lambda c: c.index)
    markers.loops.sort(key=lambda lp: lp.index)
    return markers, warnings


def _cstring(data: bytes) -> str:
    nul = data.find(b"\x00")
    if nul != -1:
        data = data[:nul]
    return data.decode("utf-8", errors="replace")


def _parse_cue(data: bytes) -> Cue:
    index = data[1]
    (position,) = struct.unpack(">I", data[2:6])
    color = Color.from_bytes(data[7:10])
    return Cue(index=index, position_ms=position, color=color, name=_cstring(data[12:]))


def _parse_loop(data: bytes) -> Loop:
    index = data[1]
    start, end = struct.unpack(">II", data[2:10])
    color = Color.from_bytes(data[15:18])
    locked = bool(data[19])
    return Loop(
        index=index,
        start_ms=start,
        end_ms=end,
        color=color,
        name=_cstring(data[20:]),
        locked=locked,
    )
