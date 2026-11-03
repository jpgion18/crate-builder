"""Builders for synthetic audio files, Serato tags, crates and databases.

Everything here writes only inside a pytest tmp_path. The encoders are the
inverse of the package's decoders and exist only for tests; the package itself
never writes Serato data.
"""

from __future__ import annotations

import base64
import struct
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from mutagen.aiff import AIFF
from mutagen.flac import FLAC
from mutagen.id3 import GEOB, ID3, TIT2, TPE1
from mutagen.mp4 import MP4, MP4FreeForm

from crate_builder.seratobox.serato.tlv import encode_record, encode_str

# ---------------------------------------------------------------- Serato payloads


@dataclass
class FCue:
    index: int
    ms: int
    rgb: tuple[int, int, int] = (0xCC, 0x00, 0x00)
    name: str = ""


@dataclass
class FLoop:
    index: int
    start_ms: int
    end_ms: int
    rgb: tuple[int, int, int] = (0x27, 0xAA, 0xE1)
    name: str = ""
    locked: bool = False


@dataclass
class FTrack:
    cues: list[FCue] = field(default_factory=list)
    loops: list[FLoop] = field(default_factory=list)
    track_color: tuple[int, int, int] | None = (0xFF, 0xFF, 0xFF)
    # BeatGrid as (position_s, beats_to_next) pairs, then the terminal (position_s, bpm).
    grid: list[tuple[float, float]] | None = None
    title: str = "Test Title"
    artist: str = "Test Artist"


def _entry(name: str, data: bytes) -> bytes:
    return name.encode("ascii") + b"\x00" + struct.pack(">I", len(data)) + data


def markers2_payload(t: FTrack) -> bytes:
    out = b"\x01\x01"
    if t.track_color is not None:
        out += _entry("COLOR", b"\x00" + bytes(t.track_color))
    for c in t.cues:
        data = (
            b"\x00"
            + bytes([c.index])
            + struct.pack(">I", c.ms)
            + b"\x00"
            + bytes(c.rgb)
            + b"\x00\x00"
            + c.name.encode("utf-8")
            + b"\x00"
        )
        out += _entry("CUE", data)
    for lp in t.loops:
        data = (
            b"\x00"
            + bytes([lp.index])
            + struct.pack(">II", lp.start_ms, lp.end_ms)
            + b"\xff\xff\xff\xff"
            + b"\x00"
            + bytes(lp.rgb)
            + b"\x00"
            + bytes([int(lp.locked)])
            + lp.name.encode("utf-8")
            + b"\x00"
        )
        out += _entry("LOOP", data)
    out += _entry("BPMLOCK", b"\x00")
    return out + b"\x00"


def wrap_markers2(payload: bytes) -> bytes:
    """What Serato puts in the GEOB: 01 01, unpadded base64 wrapped at 72, NUL padding."""
    b64 = base64.b64encode(payload).rstrip(b"=")
    lines = b"\n".join(b64[i : i + 72] for i in range(0, len(b64), 72))
    data = b"\x01\x01" + lines + b"\x00"
    return data.ljust(470, b"\x00")


def beatgrid_bytes(grid: list[tuple[float, float]]) -> bytes:
    out = b"\x01\x00" + struct.pack(">I", len(grid))
    for i, (pos, value) in enumerate(grid):
        if i == len(grid) - 1:
            out += struct.pack(">ff", pos, value)
        else:
            out += struct.pack(">fI", pos, int(value))
    return out + b"\x00"


def envelope(desc: str, data: bytes) -> str:
    """Base64 GEOB-style envelope used by M4A atoms and FLAC comments."""
    blob = b"application/octet-stream\x00\x00" + desc.encode("ascii") + b"\x00" + data
    b64 = base64.b64encode(blob).decode("ascii").rstrip("=")
    return "\n".join(b64[i : i + 72] for i in range(0, len(b64), 72))


# ---------------------------------------------------------------- audio files

MP3_FRAME_HEADER = b"\xff\xfb\x90\x00"  # MPEG-1 Layer III, 128 kbps, 44.1 kHz, stereo, no CRC
MP3_FRAME_SIZE = 417


def make_mp3(
    path: Path,
    frames: int = 40,
    xing: bool = True,
    lame: bool = True,
    delay: int = 576,
    padding: int = 1152,
) -> Path:
    body = b""
    if xing:
        info = bytearray(MP3_FRAME_SIZE)
        info[:4] = MP3_FRAME_HEADER
        off = 4 + 32
        info[off : off + 4] = b"Info"
        info[off + 4 : off + 8] = struct.pack(">I", 0x0F)
        info[off + 8 : off + 12] = struct.pack(">I", frames)
        info[off + 12 : off + 16] = struct.pack(">I", frames * MP3_FRAME_SIZE)
        lame_at = off + 8 + 4 + 4 + 100 + 4
        if lame:
            info[lame_at : lame_at + 9] = b"LAME3.100"
            info[lame_at + 21] = delay >> 4
            info[lame_at + 22] = ((delay & 0x0F) << 4) | (padding >> 8)
            info[lame_at + 23] = padding & 0xFF
        body += bytes(info)
    frame = MP3_FRAME_HEADER + bytes(MP3_FRAME_SIZE - 4)
    body += frame * frames
    path.write_bytes(body)
    return path


def make_flac(path: Path, seconds: int = 1, rate: int = 44100) -> Path:
    total = rate * seconds
    packed = (rate << 44) | ((2 - 1) << 41) | ((16 - 1) << 36) | total
    streaminfo = struct.pack(">HH", 4096, 4096) + b"\x00" * 6 + struct.pack(">Q", packed)
    streaminfo += b"\x00" * 16
    header = bytes([0x80]) + len(streaminfo).to_bytes(3, "big")  # last block, STREAMINFO
    path.write_bytes(b"fLaC" + header + streaminfo)
    return path


def _extended80(value: int) -> bytes:
    exponent = 16383 + value.bit_length() - 1
    mantissa = value << (64 - value.bit_length())
    return struct.pack(">HQ", exponent, mantissa)


def make_aiff(path: Path, seconds: int = 1, rate: int = 44100) -> Path:
    frames = rate * seconds // 10  # keep the file small; duration isn't asserted exactly
    comm = struct.pack(">hIh", 2, frames, 16) + _extended80(rate)
    sound = bytes(frames * 4)
    ssnd = struct.pack(">II", 0, 0) + sound
    chunks = b"COMM" + struct.pack(">I", len(comm)) + comm
    chunks += b"SSND" + struct.pack(">I", len(ssnd)) + ssnd
    path.write_bytes(b"FORM" + struct.pack(">I", 4 + len(chunks)) + b"AIFF" + chunks)
    return path


def _atom(name: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", 8 + len(payload)) + name + payload


def _full(name: bytes, payload: bytes, version_flags: int = 0) -> bytes:
    return _atom(name, struct.pack(">I", version_flags) + payload)


def _esds() -> bytes:
    """Minimal AAC-LC elementary stream descriptor, 44.1 kHz stereo."""
    asc = b"\x05\x02\x12\x10"  # DecoderSpecificInfo: AAC LC, 44100 Hz, 2 channels
    dcd = b"\x40\x15" + bytes(3) + struct.pack(">II", 128000, 128000) + asc
    es = struct.pack(">HB", 1, 0) + b"\x04" + bytes([len(dcd)]) + dcd + b"\x06\x01\x02"
    return _full(b"esds", b"\x03" + bytes([len(es)]) + es)


def make_m4a(path: Path, seconds: int = 1, rate: int = 44100) -> Path:
    matrix = struct.pack(">9I", 0x10000, 0, 0, 0, 0x10000, 0, 0, 0, 0x40000000)
    mvhd = _full(
        b"mvhd",
        struct.pack(">IIII", 0, 0, 1000, 1000 * seconds)
        + struct.pack(">IH", 0x10000, 0x100)
        + bytes(10)
        + matrix
        + bytes(24)
        + struct.pack(">I", 2),
    )
    tkhd = _full(
        b"tkhd",
        struct.pack(">IIIII", 0, 0, 1, 0, 1000 * seconds)
        + bytes(8)
        + struct.pack(">hhhh", 0, 0, 0x100, 0)
        + matrix
        + struct.pack(">II", 0, 0),
        7,
    )
    mdhd = _full(
        b"mdhd", struct.pack(">IIII", 0, 0, rate, rate * seconds) + struct.pack(">HH", 0x55C4, 0)
    )
    hdlr = _full(b"hdlr", struct.pack(">I", 0) + b"soun" + bytes(12) + b"\x00")
    mp4a = _atom(
        b"mp4a",
        bytes(6)
        + struct.pack(">H", 1)
        + bytes(8)
        + struct.pack(">HHHH", 2, 16, 0, 0)
        + struct.pack(">I", rate << 16)
        + _esds(),
    )
    stsd = _full(b"stsd", struct.pack(">I", 1) + mp4a)
    stbl = _atom(
        b"stbl",
        stsd
        + _full(b"stts", struct.pack(">I", 0))
        + _full(b"stsc", struct.pack(">I", 0))
        + _full(b"stsz", struct.pack(">II", 0, 0))
        + _full(b"stco", struct.pack(">I", 0)),
    )
    dinf = _atom(b"dinf", _full(b"dref", struct.pack(">I", 1) + _full(b"url ", b"", 1)))
    minf = _atom(b"minf", _full(b"smhd", struct.pack(">HH", 0, 0)) + dinf + stbl)
    trak = _atom(b"trak", tkhd + _atom(b"mdia", mdhd + hdlr + minf))
    moov = _atom(b"moov", mvhd + trak)
    ftyp = _atom(b"ftyp", b"M4A " + struct.pack(">I", 0) + b"M4A mp42isom")
    path.write_bytes(ftyp + moov + _atom(b"mdat", b""))
    return path


# ---------------------------------------------------------------- tagging (tmp copies only)


def _geob_frames(t: FTrack) -> list[GEOB]:
    frames = [
        GEOB(
            encoding=0,
            mime="application/octet-stream",
            filename="",
            desc="Serato Markers2",
            data=wrap_markers2(markers2_payload(t)),
        )
    ]
    if t.grid is not None:
        frames.append(
            GEOB(
                encoding=0,
                mime="application/octet-stream",
                filename="",
                desc="Serato BeatGrid",
                data=beatgrid_bytes(t.grid),
            )
        )
    return frames


def tag_mp3(path: Path, t: FTrack) -> None:
    tags = ID3()
    tags.add(TIT2(encoding=3, text=t.title))
    tags.add(TPE1(encoding=3, text=t.artist))
    for frame in _geob_frames(t):
        tags.add(frame)
    tags.save(path)


def tag_aiff(path: Path, t: FTrack) -> None:
    audio = AIFF(path)
    audio.add_tags()
    audio.tags.add(TIT2(encoding=3, text=t.title))
    audio.tags.add(TPE1(encoding=3, text=t.artist))
    for frame in _geob_frames(t):
        audio.tags.add(frame)
    audio.save()


def tag_flac(path: Path, t: FTrack) -> None:
    audio = FLAC(path)
    audio["title"] = t.title
    audio["artist"] = t.artist
    audio["SERATO_MARKERS_V2"] = envelope("Serato Markers2", wrap_markers2(markers2_payload(t)))
    if t.grid is not None:
        audio["SERATO_BEATGRID"] = envelope("Serato BeatGrid", beatgrid_bytes(t.grid))
    audio.save()


def tag_m4a(path: Path, t: FTrack) -> None:
    audio = MP4(path)
    audio["\xa9nam"] = t.title
    audio["\xa9ART"] = t.artist
    audio["----:com.serato.dj:markersv2"] = [
        MP4FreeForm(envelope("Serato Markers2", wrap_markers2(markers2_payload(t))).encode())
    ]
    if t.grid is not None:
        audio["----:com.serato.dj:beatgrid"] = [
            MP4FreeForm(envelope("Serato BeatGrid", beatgrid_bytes(t.grid)).encode())
        ]
    audio.save()


MAKERS = {
    "mp3": (make_mp3, tag_mp3),
    "m4a": (make_m4a, tag_m4a),
    "flac": (make_flac, tag_flac),
    "aiff": (make_aiff, tag_aiff),
}


def make_tagged(path: Path, t: FTrack) -> Path:
    make, tag = MAKERS[path.suffix.lstrip(".").lower()]
    make(path)
    tag(path, t)
    return path


# ---------------------------------------------------------------- library files


def crate_bytes(paths: list[str]) -> bytes:
    out = encode_record("vrsn", encode_str("1.0/Serato ScratchLive Crate"))
    out += encode_record(
        "osrt", encode_record("tvcn", encode_str("song")) + encode_record("brev", b"\x00")
    )
    for p in paths:
        out += encode_record("otrk", encode_record("ptrk", encode_str(p)))
    return out


def database_bytes(tracks: list[dict[str, str | int]]) -> bytes:
    out = encode_record("vrsn", encode_str("2.0/Serato Scratch LIVE Database"))
    for t in tracks:
        body = b""
        for key, value in t.items():
            if isinstance(value, int):
                body += encode_record(key, struct.pack(">I", value))
            else:
                body += encode_record(key, encode_str(value))
        out += encode_record("otrk", body)
    return out


def write_crate(serato_dir: Path, parts: tuple[str, ...], paths: list[str]) -> Path:
    sub = serato_dir / "Subcrates"
    sub.mkdir(parents=True, exist_ok=True)
    file = sub / ("%%".join(parts) + ".crate")
    file.write_bytes(crate_bytes(paths))
    return file


# ---------------------------------------------------------------- a fake library


@dataclass
class Library:
    drive: Path  # plays the role of the drive root (e.g. /Volumes/USB)
    serato: Path  # <drive>/_Serato_
    files: dict[str, Path]  # stored path -> file


TRACKS: dict[str, FTrack] = {
    "Music/House/Opener.mp3": FTrack(
        cues=[
            FCue(0, 1000, (0xCC, 0x00, 0x00), "Intro"),
            FCue(1, 32500, (0x00, 0xCC, 0x00), "Drop"),
        ],
        loops=[FLoop(0, 64000, 71500, name="Break loop")],
        grid=[(0.05, 124.0)],
        title="Opener",
        artist="DJ Test",
    ),
    "Music/House/Café Déjà Vu #1 & more.m4a": FTrack(
        cues=[FCue(0, 250, name="Start"), FCue(7, 90000, (0x88, 0x00, 0xCC), "Outro")],
        grid=[(0.2, 32), (15.683, 32), (31.2, 122.5)],  # variable grid
        title="Café Déjà Vu",
        artist="Ünïcødé",
    ),
    "Music/Deep/Low End.flac": FTrack(
        cues=[FCue(2, 12345, name="Vox")],
        loops=[FLoop(1, 20000, 22000), FLoop(2, 40000, 44000, name="Bars")],
        grid=None,  # no beatgrid
        title="Low End",
        artist="Sub",
    ),
    "Music/Deep/Warehouse.aiff": FTrack(
        cues=[], loops=[], grid=[(0.0, 128.0)], title="Warehouse", artist="Sub"
    ),
}


@pytest.fixture
def library(tmp_path: Path) -> Library:
    drive = tmp_path / "Drive"
    serato = drive / "_Serato_"
    serato.mkdir(parents=True)
    files: dict[str, Path] = {}
    for stored, track in TRACKS.items():
        path = drive / stored
        path.parent.mkdir(parents=True, exist_ok=True)
        files[stored] = make_tagged(path, track)
    write_crate(
        serato, ("House",), ["Music/House/Opener.mp3", "Music/House/Café Déjà Vu #1 & more.m4a"]
    )
    write_crate(serato, ("House", "Deep"), ["Music/Deep/Low End.flac", "Music/Deep/Warehouse.aiff"])
    write_crate(serato, ("Missing",), ["Music/Nowhere/ghost.mp3", "Music/House/Opener.mp3"])
    (serato / "database V2").write_bytes(
        database_bytes(
            [
                {
                    "pfil": "Music/House/Opener.mp3",
                    "tsng": "Opener (DB)",
                    "tkey": "8A",
                    "uadd": 1700000000,
                },
                {"pfil": "Music/Deep/Low End.flac", "tbpm": "121.00", "tgen": "Deep House"},
            ]
        )
    )
    return Library(drive=drive, serato=serato, files=files)
