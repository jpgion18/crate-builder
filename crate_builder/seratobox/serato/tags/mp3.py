"""MP3: Serato data in ID3v2 GEOB frames, plus first-frame gapless info.

We also read the Xing/Info header and LAME extension from the first MPEG frame,
because decoders disagree on whether that frame and the encoder delay count as
audio, which can shift cue positions between applications.
"""

from __future__ import annotations

import struct
from pathlib import Path

from mutagen.mp3 import MP3

from ..models import Mp3Framing, TrackTags
from .common import fill_stream_info
from .id3 import read_id3

_BITRATES = {
    # (mpeg1, layer3) and (mpeg2/2.5, layer3), kbps
    True: [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0],
    False: [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0],
}
_SAMPLE_RATES = {3: [44100, 48000, 32000], 2: [22050, 24000, 16000], 0: [11025, 12000, 8000]}


def read_mp3(path: Path) -> TrackTags:
    tags = TrackTags()
    audio = MP3(path)
    fill_stream_info(tags, audio.info)
    read_id3(tags, audio.tags, "MP3 GEOB")
    tags.mp3_framing = read_mp3_framing(path)
    return tags


def read_mp3_framing(path: Path) -> Mp3Framing:
    with path.open("rb") as fh:
        head = fh.read(10)
        offset = 0
        if head[:3] == b"ID3" and len(head) == 10:
            size = (head[6] << 21) | (head[7] << 14) | (head[8] << 7) | head[9]
            offset = 10 + size + (10 if head[5] & 0x10 else 0)
        fh.seek(offset)
        data = fh.read(64 * 1024)
    return parse_first_frame(data)


def parse_first_frame(data: bytes) -> Mp3Framing:
    framing = Mp3Framing()
    pos = _find_sync(data)
    if pos is None or pos + 4 > len(data):
        return framing
    (header,) = struct.unpack(">I", data[pos : pos + 4])
    version_bits = (header >> 19) & 0x3
    rate_index = (header >> 10) & 0x3
    has_crc = not ((header >> 16) & 0x1)
    mono = ((header >> 6) & 0x3) == 3
    if version_bits == 1 or rate_index == 3:
        return framing
    framing.sample_rate = _SAMPLE_RATES[version_bits][rate_index]
    mpeg1 = version_bits == 3
    side_info = (17 if mono else 32) if mpeg1 else (9 if mono else 17)
    xing = pos + 4 + (2 if has_crc else 0) + side_info
    tag = data[xing : xing + 4]
    if tag not in (b"Xing", b"Info") or xing + 8 > len(data):
        return framing
    framing.has_xing = True
    (flags,) = struct.unpack(">I", data[xing + 4 : xing + 8])
    lame = xing + 8
    lame += 4 if flags & 0x1 else 0  # frames
    lame += 4 if flags & 0x2 else 0  # bytes
    lame += 100 if flags & 0x4 else 0  # TOC
    lame += 4 if flags & 0x8 else 0  # quality
    encoder = data[lame : lame + 4]
    if encoder not in (b"LAME", b"Lavf", b"Lavc", b"L3.9") or lame + 24 > len(data):
        return framing
    framing.has_lame = True
    b0, b1, b2 = data[lame + 21 : lame + 24]
    framing.encoder_delay = (b0 << 4) | (b1 >> 4)
    framing.padding = ((b1 & 0x0F) << 8) | b2
    return framing


def _find_sync(data: bytes) -> int | None:
    pos = 0
    while True:
        pos = data.find(b"\xff", pos)
        if pos == -1 or pos + 1 >= len(data):
            return None
        b1 = data[pos + 1]
        # 11 sync bits, layer III (bits 01)
        if (b1 & 0xE0) == 0xE0 and ((b1 >> 1) & 0x3) == 1:
            return pos
        pos += 1
