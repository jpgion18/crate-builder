"""export_playlist(): audio files straight into a Rekordbox playlist, no Serato folder."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from seratobox_fixtures import FCue, FTrack, Library, make_mp3, make_tagged

from crate_builder.seratobox import ConvertError, ConvertOptions, export_playlist
from crate_builder.seratobox.rekordbox import validate_file
from crate_builder.seratobox.serato.models import DatabaseTrack


def test_nested_playlist_with_serato_cues_and_metadata(library: Library, tmp_path: Path) -> None:
    opener = library.files["Music/House/Opener.mp3"]
    low_end = library.files["Music/Deep/Low End.flac"]
    out = tmp_path / "out.xml"
    report = export_playlist(
        [opener, low_end, opener, tmp_path / "gone.mp3"],  # duplicate and missing file
        "Gigs > Friday",
        out,
        metadata={str(low_end): DatabaseTrack(path=str(low_end), title="Low End (scan)")},
    )
    assert report.written and validate_file(out) == []
    assert [t.found for t in report.tracks] == [True, True, False]
    root = ET.parse(out).getroot()
    names = [t.get("Name") for t in root.iterfind("COLLECTION/TRACK")]
    assert names == ["Opener", "Low End (scan)"]
    marks = root.find("COLLECTION/TRACK").findall("POSITION_MARK")
    assert [m.get("Name") for m in marks if m.get("Num") == "0"] == ["Intro"]  # Serato cue kept
    folder = root.find("PLAYLISTS/NODE/NODE")
    assert (folder.get("Name"), folder.get("Type")) == ("Gigs", "0")
    playlist = folder.find("NODE")
    assert (playlist.get("Name"), playlist.get("Entries")) == ("Friday", "2")


def test_rekordbox_only_library_has_no_serato_notes(tmp_path: Path) -> None:
    plain = make_mp3(tmp_path / "plain.mp3")  # never touched by Serato
    report = export_playlist([plain], "Warmup", tmp_path / "out.xml", serato_notes=False)
    assert report.tracks[0].warnings == []
    noisy = export_playlist([plain], "Warmup", None, ConvertOptions(dry_run=True))
    assert "No Serato beatgrid" in noisy.tracks[0].warnings


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    track = make_tagged(tmp_path / "a.flac", FTrack(cues=[FCue(0, 500)]))
    report = export_playlist([track], "X", None, ConvertOptions(dry_run=True))
    assert not report.written and report.tracks[0].hot_cues == 1


@pytest.mark.parametrize("name", ["", "  >  "])
def test_empty_name_rejected(tmp_path: Path, name: str) -> None:
    with pytest.raises(ConvertError, match="empty"):
        export_playlist([make_mp3(tmp_path / "a.mp3")], name, tmp_path / "o.xml")


def test_no_tracks_or_unsafe_output_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConvertError, match="No tracks"):
        export_playlist([], "X", tmp_path / "o.xml")
    track = make_mp3(tmp_path / "a.mp3")
    with pytest.raises(ConvertError, match="audio file"):
        export_playlist([track], "X", track)
