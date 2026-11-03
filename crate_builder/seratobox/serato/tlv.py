"""Serato's tag-length-value container format, shared by `.crate` files and `database V2`.

Each record is a 4-byte ASCII tag, a 4-byte big-endian length, then `length` bytes.
The first letter of the tag gives the value type:

    o  nested records        t, p  UTF-16BE string (text, path)
    u  uint32 BE             s     uint16 BE
    b  single byte (bool)

`vrsn` is a UTF-16BE string despite the `v`.
"""

from __future__ import annotations

import struct
from collections.abc import Iterator

Record = tuple[str, bytes]


class TLVError(ValueError):
    pass


def iter_records(data: bytes) -> Iterator[Record]:
    pos = 0
    end = len(data)
    while pos < end:
        if end - pos < 8:
            raise TLVError(f"truncated record header at byte {pos}")
        tag_raw = data[pos : pos + 4]
        (length,) = struct.unpack(">I", data[pos + 4 : pos + 8])
        pos += 8
        if pos + length > end:
            raise TLVError(f"record {tag_raw!r} at byte {pos - 8} overruns buffer")
        try:
            tag = tag_raw.decode("ascii")
        except UnicodeDecodeError as exc:
            raise TLVError(f"non-ASCII tag {tag_raw!r} at byte {pos - 8}") from exc
        yield tag, data[pos : pos + length]
        pos += length


def decode_str(value: bytes) -> str:
    return value.decode("utf-16-be", errors="replace").rstrip("\x00")


def decode_u32(value: bytes) -> int:
    return int(struct.unpack(">I", value[:4])[0]) if len(value) >= 4 else 0


def encode_str(value: str) -> bytes:
    return value.encode("utf-16-be")


def encode_record(tag: str, value: bytes) -> bytes:
    return tag.encode("ascii") + struct.pack(">I", len(value)) + value
