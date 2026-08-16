"""Parse Serato's database V2 file — every track Serato knows about, with
its own metadata (Mixed In Key energy, key, grouping tags, etc.), separate
from any one .crate.

Same TLV chunk format .crate files use (tag[4] + big-endian length[4] +
payload — see serato_crate.py), but nested: each top-level `otrk` chunk's
payload is itself a sequence of the same tag/length/payload chunks, one per
track field. Not officially documented by Serato; this schema was confirmed
against a real 6,389-track library (see the "Serato Library Cleaner"
concept/handoff this was ported from).

A field's first tag letter says how to decode its payload: `t`/`p` is
UTF-16BE text, `u` a big-endian uint32, `s` a big-endian uint16, `b` a
single-byte bool.
"""

from __future__ import annotations

import os
import re
import struct
from dataclasses import dataclass

from crate_builder.serato_paths import is_windows

_TEXT_TAG_PREFIXES = ("t", "p")
_ENERGY_PATTERN = re.compile(r"Energy\s*(\d+)", re.IGNORECASE)


class SeratoDatabaseError(RuntimeError):
    pass


@dataclass
class SeratoDbTrack:
    path: str
    title: str
    artist: str
    album: str = ""
    year: str = ""
    key: str = ""
    energy: int | None = None
    grouping: str = ""
    source: str = ""
    bpm: str = ""


def resolve_serato_path(pfil: str) -> str:
    """Reverses serato_crate.to_serato_relative_path(): Serato stores an
    absolute path with the leading '/' stripped (macOS/Linux) or, on
    Windows, the drive-lettered path as-is (never starts with '/', so
    nothing to strip in the first place)."""
    if not pfil:
        return ""
    if is_windows() or pfil[1:2] == ":":
        return pfil
    return pfil if pfil.startswith("/") else "/" + pfil


def _decode_leaf(tag: str, data: bytes):
    kind = tag[0] if tag else ""
    try:
        if kind in _TEXT_TAG_PREFIXES:
            return data.decode("utf-16-be").rstrip("\x00")
        if kind == "u" and len(data) == 4:
            return struct.unpack(">I", data)[0]
        if kind == "s" and len(data) == 2:
            return struct.unpack(">H", data)[0]
        if kind == "b" and len(data) == 1:
            return data[0] != 0
    except (UnicodeDecodeError, struct.error):
        return None
    return None


def _read_chunks(data: bytes, start: int, end: int) -> list[tuple[str, bytes]]:
    chunks: list[tuple[str, bytes]] = []
    pos = start
    while pos + 8 <= end:
        tag = data[pos : pos + 4].decode("ascii", errors="replace")
        length = struct.unpack(">I", data[pos + 4 : pos + 8])[0]
        payload_start = pos + 8
        payload_end = payload_start + length
        if payload_end > end:
            break
        chunks.append((tag, data[payload_start:payload_end]))
        pos = payload_end
    return chunks


def _to_track(fields: dict) -> SeratoDbTrack:
    comment = fields.get("tcom") or ""
    energy_match = _ENERGY_PATTERN.search(comment)
    return SeratoDbTrack(
        path=resolve_serato_path(fields.get("pfil") or ""),
        title=(fields.get("tsng") or "").strip(),
        artist=(fields.get("tart") or "").strip(),
        album=(fields.get("talb") or "").strip(),
        year=(fields.get("ttyr") or "").strip(),
        key=fields.get("tkey") or "",
        energy=int(energy_match.group(1)) if energy_match else None,
        grouping=fields.get("tgrp") or "",
        source=fields.get("tcmp") or fields.get("trmx") or "",
        bpm=fields.get("tbpm") or "",
    )


def parse_database(path: str) -> list[SeratoDbTrack]:
    if not os.path.isfile(path):
        raise SeratoDatabaseError(f"Serato database not found: {path}")

    with open(path, "rb") as f:
        data = f.read()

    tracks: list[SeratoDbTrack] = []
    for tag, payload in _read_chunks(data, 0, len(data)):
        if tag != "otrk":
            continue
        fields = {ftag: _decode_leaf(ftag, fpayload) for ftag, fpayload in _read_chunks(payload, 0, len(payload))}
        tracks.append(_to_track(fields))
    return tracks
