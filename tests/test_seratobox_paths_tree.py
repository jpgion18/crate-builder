"""Windows path handling and the crate tree used by the Rekordbox tab."""

from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath

from seratobox_fixtures import write_crate

from crate_builder.seratobox.rekordbox import location_uri
from crate_builder.seratobox.serato.crates import crate_tree, read_all_crates
from crate_builder.seratobox.serato.paths import (
    candidate_paths,
    drive_root_of,
    is_absolute_stored,
    resolve_track_path,
)


def test_drive_root_macos() -> None:
    assert drive_root_of(PurePosixPath("/Volumes/USB/_Serato_")) == PurePosixPath("/Volumes/USB")
    assert drive_root_of(PurePosixPath("/Users/joey/Music/_Serato_")) == PurePosixPath("/")


def test_drive_root_windows() -> None:
    assert drive_root_of(PureWindowsPath(r"C:\Users\joey\Music\_Serato_")) == PureWindowsPath("C:\\")
    assert drive_root_of(PureWindowsPath(r"E:\_Serato_")) == PureWindowsPath("E:\\")


def test_absolute_stored_paths() -> None:
    assert is_absolute_stored("C:/Users/joey/Music/a.mp3")  # Crate Builder on Windows
    assert is_absolute_stored("/Users/joey/Music/a.mp3")
    assert not is_absolute_stored("Users/joey/Music/a.mp3")  # Serato's own form
    assert candidate_paths("C:\\Music\\a.mp3", Path("/x/_Serato_"))[0] == Path("C:/Music/a.mp3")


def test_crate_builder_style_path_resolves(tmp_path: Path) -> None:
    """Crate Builder writes the full path minus its leading slash."""
    serato = tmp_path / "Music" / "_Serato_"
    serato.mkdir(parents=True)
    track = tmp_path / "elsewhere" / "a.mp3"
    track.parent.mkdir()
    track.write_bytes(b"x")
    stored = str(track).lstrip("/")
    assert resolve_track_path(stored, serato) == track


def test_location_uri_windows() -> None:
    uri = location_uri(PureWindowsPath(r"C:\Users\Joey\Música\Café #1.mp3"))
    assert uri == "file://localhost/C:/Users/Joey/M%C3%BAsica/Caf%C3%A9%20%231.mp3"
    assert location_uri(PureWindowsPath("E:\\a b.flac")) == "file://localhost/E:/a%20b.flac"


def test_location_uri_macos() -> None:
    assert location_uri(PurePosixPath("/Users/j/a b.mp3")) == "file://localhost/Users/j/a%20b.mp3"


def test_crate_tree_nests_and_fills_missing_parents(tmp_path: Path) -> None:
    for parts in [("b",), ("A", "Deep"), ("A",), ("Z", "Only child")]:
        write_crate(tmp_path, parts, ["x.mp3"])
    roots = crate_tree(read_all_crates(tmp_path))
    assert [n.name for n in roots] == ["A", "b", "Z"]
    a, _, z = roots
    assert [c.ref for c in a.children] == ["A%%Deep"]
    assert z.crate is None and z.track_count == 0  # no Z.crate file
    assert z.children[0].ref == "Z%%Only child" and z.children[0].track_count == 1
