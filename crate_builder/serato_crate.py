"""Read/write Serato DJ .crate files.

The .crate format is not officially documented by Serato; this is based on
community reverse-engineering (widely used by other open-source Serato
tools). It's a flat sequence of tag/length/value chunks:

    4 bytes  ASCII tag (e.g. "vrsn", "otrk", "ptrk")
    4 bytes  big-endian uint32 length of the value
    N bytes  value (text values are UTF-16BE, no BOM)

A minimal crate is a "vrsn" chunk followed by one "otrk" chunk per track,
each "otrk" wrapping a single "ptrk" chunk holding the track's file path
relative to the volume root (i.e. an absolute path with the leading slash
stripped).

Always keep a backup of your _Serato_ folder before writing to it, and
verify a newly built crate opens correctly in Serato before relying on it.
"""

from __future__ import annotations

import os
import struct

CRATE_VERSION = "1.0/Serato ScratchLive Crate"


def _encode_text(text: str) -> bytes:
    return text.encode("utf-16-be")


def _decode_text(data: bytes) -> str:
    return data.decode("utf-16-be")


def _write_chunk(tag: str, value: bytes) -> bytes:
    return tag.encode("ascii") + struct.pack(">I", len(value)) + value


def _read_chunks(data: bytes) -> list[tuple[str, bytes]]:
    chunks = []
    pos = 0
    while pos + 8 <= len(data):
        tag = data[pos : pos + 4].decode("ascii")
        length = struct.unpack(">I", data[pos + 4 : pos + 8])[0]
        value = data[pos + 8 : pos + 8 + length]
        chunks.append((tag, value))
        pos += 8 + length
    return chunks


def to_serato_relative_path(path: str) -> str:
    """Convert an absolute filesystem path to Serato's crate path format."""
    path = os.path.abspath(path).replace("\\", "/")
    if path.startswith("/"):
        path = path[1:]
    return path


def build_crate_bytes(track_paths: list[str]) -> bytes:
    out = bytearray()
    out += _write_chunk("vrsn", _encode_text(CRATE_VERSION))
    for path in track_paths:
        ptrk = _write_chunk("ptrk", _encode_text(to_serato_relative_path(path)))
        out += _write_chunk("otrk", ptrk)
    return bytes(out)


def write_crate(dest_path: str, track_paths: list[str], overwrite: bool = False) -> str:
    if os.path.exists(dest_path) and not overwrite:
        raise FileExistsError(f"Crate already exists: {dest_path}")
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    with open(dest_path, "wb") as f:
        f.write(build_crate_bytes(track_paths))
    return dest_path


def read_crate_track_paths(path: str) -> list[str]:
    with open(path, "rb") as f:
        data = f.read()
    paths = []
    for tag, value in _read_chunks(data):
        if tag == "otrk":
            for sub_tag, sub_value in _read_chunks(value):
                if sub_tag == "ptrk":
                    paths.append(_decode_text(sub_value))
    return paths
