"""Per-format round trips: write known Serato tags to a generated file, read them back."""

from __future__ import annotations

from pathlib import Path

import pytest
from mutagen.flac import FLAC
from mutagen.id3 import GEOB, ID3
from mutagen.mp4 import MP4, MP4FreeForm
from seratobox_fixtures import (
    MAKERS,
    FCue,
    FLoop,
    FTrack,
    make_mp3,
    make_tagged,
)

from crate_builder.seratobox.serato.tags import read_tags
from crate_builder.seratobox.serato.tags.mp3 import read_mp3_framing

FORMATS = ["mp3", "m4a", "flac", "aiff"]

KNOWN = FTrack(
    cues=[
        FCue(0, 0, name="Zero"),
        FCue(1, 1, name="One ms"),
        FCue(4, 123_456, (0x00, 0xCC, 0xCC), "Mid ✨"),
        FCue(7, 3_599_999, name="Last slot"),
    ],
    loops=[FLoop(0, 10_000, 12_345, name="Four bars"), FLoop(7, 500, 501)],
    grid=[(0.0371, 127.93)],
    title="Tïtle",
    artist="Ärtist",
)


@pytest.mark.parametrize("fmt", FORMATS)
def test_round_trip(tmp_path: Path, fmt: str) -> None:
    path = make_tagged(tmp_path / f"t.{fmt}", KNOWN)
    tags = read_tags(path)
    assert tags.warnings == []
    assert tags.markers is not None
    assert [(c.index, c.position_ms, c.name) for c in tags.markers.cues] == [
        (c.index, c.ms, c.name) for c in KNOWN.cues
    ]
    assert [(lp.index, lp.start_ms, lp.end_ms, lp.name) for lp in tags.markers.loops] == [
        (lp.index, lp.start_ms, lp.end_ms, lp.name) for lp in KNOWN.loops
    ]
    assert tags.markers.cues[2].color is not None
    assert tags.markers.cues[2].color.hex() == "#00CCCC"
    assert tags.beatgrid is not None and len(tags.beatgrid) == 1
    assert tags.beatgrid[0].position_s == pytest.approx(0.0371, abs=1e-6)
    assert tags.beatgrid[0].bpm == pytest.approx(127.93, abs=1e-4)
    assert (tags.title, tags.artist) == ("Tïtle", "Ärtist")
    assert tags.duration_s and tags.duration_s > 0


@pytest.mark.parametrize("fmt", FORMATS)
def test_untagged_file(tmp_path: Path, fmt: str) -> None:
    make, _ = MAKERS[fmt]
    tags = read_tags(make(tmp_path / f"t.{fmt}"))
    assert tags.markers is None and tags.beatgrid is None
    assert tags.warnings == []


@pytest.mark.parametrize("fmt", FORMATS)
def test_corrupt_file_does_not_raise(tmp_path: Path, fmt: str) -> None:
    path = tmp_path / f"t.{fmt}"
    path.write_bytes(b"not audio at all")
    tags = read_tags(path)
    assert tags.markers is None
    assert tags.warnings and "Could not read tags" in tags.warnings[0]


def test_malformed_markers_mp3(tmp_path: Path) -> None:
    path = make_mp3(tmp_path / "t.mp3")
    id3 = ID3()
    id3.add(
        GEOB(
            encoding=0,
            mime="application/octet-stream",
            filename="",
            desc="Serato Markers2",
            data=b"\x09\x09garbage",
        )
    )
    id3.add(
        GEOB(
            encoding=0,
            mime="application/octet-stream",
            filename="",
            desc="Serato BeatGrid",
            data=b"\x01\x00\x00\x00\x00\x09",
        )
    )
    id3.save(path)
    tags = read_tags(path)
    assert tags.markers is None and tags.beatgrid is None
    assert any("Markers2" in w for w in tags.warnings)
    assert any("BeatGrid" in w for w in tags.warnings)


def test_malformed_markers_flac(tmp_path: Path) -> None:
    path = MAKERS["flac"][0](tmp_path / "t.flac")
    audio = FLAC(path)
    audio["SERATO_MARKERS_V2"] = "!!!not base64!!!"
    audio.save()
    tags = read_tags(path)
    assert tags.markers is None and any("Markers2" in w for w in tags.warnings)


def test_malformed_markers_m4a(tmp_path: Path) -> None:
    path = MAKERS["m4a"][0](tmp_path / "t.m4a")
    audio = MP4(path)
    audio["----:com.serato.dj:markersv2"] = [MP4FreeForm(b"AAAA")]
    audio.save()
    tags = read_tags(path)
    assert tags.markers is None and any("Markers2" in w for w in tags.warnings)


def test_unsupported_extension(tmp_path: Path) -> None:
    path = tmp_path / "t.ogg"
    path.write_bytes(b"x")
    assert "Unsupported" in read_tags(path).warnings[0]


def test_mp3_framing_lame(tmp_path: Path) -> None:
    framing = read_mp3_framing(make_tagged(tmp_path / "t.mp3", KNOWN))  # ID3 tag in front
    assert (framing.has_xing, framing.has_lame) == (True, True)
    assert (framing.encoder_delay, framing.padding, framing.sample_rate) == (576, 1152, 44100)


def test_mp3_framing_xing_without_lame(tmp_path: Path) -> None:
    framing = read_mp3_framing(make_mp3(tmp_path / "t.mp3", lame=False))
    assert (framing.has_xing, framing.has_lame, framing.encoder_delay) == (True, False, None)


def test_mp3_framing_no_header(tmp_path: Path) -> None:
    framing = read_mp3_framing(make_mp3(tmp_path / "t.mp3", xing=False))
    assert (framing.has_xing, framing.sample_rate) == (False, 44100)
