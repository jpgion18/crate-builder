"""Crates, database V2 and path resolution."""

from __future__ import annotations

import unicodedata
from pathlib import Path

import pytest
from seratobox_fixtures import crate_bytes, database_bytes, write_crate

from crate_builder.seratobox.serato.crates import (
    crate_parts_from_filename,
    parse_crate_bytes,
    parse_crate_name,
    read_all_crates,
    select_crates,
)
from crate_builder.seratobox.serato.database import parse_database_bytes, read_database
from crate_builder.seratobox.serato.paths import drive_root_for, resolve_track_path
from crate_builder.seratobox.serato.tlv import TLVError


def test_crate_round_trip_with_unicode() -> None:
    paths = ["Music/a.mp3", "Users/joey/Música/Ñandú (Edit).flac"]
    assert parse_crate_bytes(crate_bytes(paths)) == paths


def test_crate_nesting_from_filename() -> None:
    assert crate_parts_from_filename("House%%Deep%%Late.crate") == ("House", "Deep", "Late")
    assert crate_parts_from_filename("Solo.crate") == ("Solo",)


@pytest.mark.parametrize(
    ("name", "parts"),
    [
        ("House%%Deep", ("House", "Deep")),
        ("House/Deep", ("House", "Deep")),
        ("House > Deep", ("House", "Deep")),
        ("House", ("House",)),
    ],
)
def test_parse_crate_name(name: str, parts: tuple[str, ...]) -> None:
    assert parse_crate_name(name) == parts


def test_select_crates_includes_subcrates(tmp_path: Path) -> None:
    for parts in [("House",), ("House", "Deep"), ("House", "Deep", "Late"), ("Techno",)]:
        write_crate(tmp_path, parts, [])
    crates = read_all_crates(tmp_path)
    selected, missing = select_crates(crates, ["house", "Nope"])
    assert [c.parts for c in selected] == [("House",), ("House", "Deep"), ("House", "Deep", "Late")]
    assert missing == ["Nope"]
    only, _ = select_crates(crates, ["House/Deep"], include_subcrates=False)
    assert [c.parts for c in only] == [("House", "Deep")]


def test_corrupt_crate_is_skipped_with_warning(tmp_path: Path) -> None:
    write_crate(tmp_path, ("Good",), ["a.mp3"])
    (tmp_path / "Subcrates" / "Bad.crate").write_bytes(b"otrk\x00\x00\xff\xff")
    warnings: list[str] = []
    crates = read_all_crates(tmp_path, warnings)
    assert [c.name for c in crates] == ["Good"]
    assert "Bad.crate" in warnings[0]
    with pytest.raises(TLVError):
        read_all_crates(tmp_path)


def test_database_parsing(tmp_path: Path) -> None:
    data = database_bytes([{"pfil": "Music/a.mp3", "tsng": "A", "tbpm": "128", "uadd": 42}])
    (track,) = parse_database_bytes(data)
    assert (track.path, track.title, track.bpm, track.date_added) == ("Music/a.mp3", "A", "128", 42)


def test_missing_database_warns(tmp_path: Path) -> None:
    warnings: list[str] = []
    assert read_database(tmp_path, warnings) == {}
    assert "database V2" in warnings[0]


def test_drive_root() -> None:
    assert drive_root_for(Path("/Volumes/USB/_Serato_")) == Path("/Volumes/USB")
    assert drive_root_for(Path("/Users/joey/Music/_Serato_")) == Path("/")


def test_resolve_relative_to_drive(tmp_path: Path) -> None:
    serato = tmp_path / "_Serato_"
    serato.mkdir()
    track = tmp_path / "Music" / "a.mp3"
    track.parent.mkdir()
    track.write_bytes(b"x")
    assert resolve_track_path("Music/a.mp3", serato) == track
    assert resolve_track_path(str(track), serato) == track  # absolute stored path
    assert resolve_track_path("Music/missing.mp3", serato) is None


def test_resolve_across_unicode_normalization(tmp_path: Path) -> None:
    serato = tmp_path / "_Serato_"
    serato.mkdir()
    nfd_name = unicodedata.normalize("NFD", "Café.mp3")
    (tmp_path / nfd_name).write_bytes(b"x")
    found = resolve_track_path(unicodedata.normalize("NFC", "Café.mp3"), serato)
    assert found is not None and found.is_file()


def test_resolve_with_extra_root(tmp_path: Path) -> None:
    serato = tmp_path / "lib" / "_Serato_"
    serato.mkdir(parents=True)
    moved = tmp_path / "moved"
    (moved / "Music").mkdir(parents=True)
    (moved / "Music" / "a.mp3").write_bytes(b"x")
    assert resolve_track_path("Music/a.mp3", serato) is None
    assert resolve_track_path("Music/a.mp3", serato, [moved]) == moved / "Music" / "a.mp3"
