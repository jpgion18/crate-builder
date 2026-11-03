"""End to end: synthetic Serato library -> convert() -> Rekordbox XML."""

from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote, urlparse

import pytest
from seratobox_fixtures import Library

from crate_builder.seratobox import ConvertError, ConvertOptions, CueMode, convert
from crate_builder.seratobox.cli import main
from crate_builder.seratobox.rekordbox import validate_file


def _snapshot(root: Path) -> dict[str, tuple[str, int]]:
    return {
        str(p.relative_to(root)): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def _tracks_by_name(xml: Path) -> dict[str, ET.Element]:
    root = ET.parse(xml).getroot()
    return {t.get("Name", ""): t for t in root.iterfind("COLLECTION/TRACK")}


def test_convert_crate_end_to_end(library: Library, tmp_path: Path) -> None:
    before = _snapshot(library.drive)
    out = tmp_path / "out" / "rekordbox.xml"
    report = convert(["House"], library.serato, out)

    assert _snapshot(library.drive) == before  # read-only on library and audio
    assert report.written and out.is_file()
    assert validate_file(out) == []
    assert report.crates == ["House", "House > Deep"]
    assert len(report.tracks) == 4 and not report.missing

    tracks = _tracks_by_name(out)
    assert set(tracks) == {"Opener (DB)", "Café Déjà Vu", "Low End", "Warehouse"}

    opener = tracks["Opener (DB)"]
    assert opener.get("Tonality") == "8A" and opener.get("DateAdded") == "2023-11-14"
    marks = [
        (m.get("Type"), m.get("Num"), m.get("Start"), m.get("End"), m.get("Name"))
        for m in opener.iterfind("POSITION_MARK")
    ]
    assert marks == [
        ("0", "0", "1.000", None, "Intro"),
        ("0", "-1", "1.000", None, "Intro"),
        ("0", "1", "32.500", None, "Drop"),
        ("0", "-1", "32.500", None, "Drop"),
        ("4", "-1", "64.000", "71.500", "Break loop"),
    ]
    tempo = opener.find("TEMPO")
    assert tempo is not None and (tempo.get("Inizio"), tempo.get("Bpm")) == ("0.050", "124.00")

    cafe = tracks["Café Déjà Vu"]
    assert unquote(urlparse(cafe.get("Location", "")).path) == str(
        library.files["Music/House/Café Déjà Vu #1 & more.m4a"]
    )
    assert [m.get("Num") for m in cafe.iterfind("POSITION_MARK")] == ["0", "-1", "7", "-1"]
    cafe_tempo = cafe.findall("TEMPO")
    assert len(cafe_tempo) == 1 and cafe_tempo[0].get("Bpm") == f"{32 * 60 / (15.683 - 0.2):.2f}"

    low_end = tracks["Low End"]
    assert low_end.find("TEMPO") is None
    assert low_end.get("AverageBpm") == "121.00" and low_end.get("Genre") == "Deep House"

    root = ET.parse(out).getroot()
    house = root.find("PLAYLISTS/NODE/NODE")
    assert house is not None and (house.get("Name"), house.get("Type")) == ("House", "0")
    assert [(n.get("Name"), n.get("Type"), n.get("Entries")) for n in house.findall("NODE")] == [
        ("House", "1", "2"),
        ("Deep", "1", "2"),
    ]

    by_path = {t.stored_path: t for t in report.tracks}
    assert any("flattened" in w for w in by_path["Music/House/Café Déjà Vu #1 & more.m4a"].warnings)
    assert "No Serato beatgrid" in by_path["Music/Deep/Low End.flac"].warnings
    assert "No Serato cues or loops" not in by_path["Music/Deep/Warehouse.aiff"].warnings
    assert by_path["Music/Deep/Warehouse.aiff"].hot_cues == 0


def test_dry_run_writes_nothing(library: Library, tmp_path: Path) -> None:
    out = tmp_path / "never.xml"
    report = convert(["House"], library.serato, out, ConvertOptions(dry_run=True))
    assert not out.exists() and not report.written
    assert report.render().startswith("SeratoBox report: Dry run")
    assert convert(["House"], library.serato, None, ConvertOptions(dry_run=True)).tracks


@pytest.mark.parametrize(
    ("mode", "hot", "memory", "loop_nums"),
    [
        (CueMode.BOTH, ["0", "1"], 2, ["-1"]),
        (CueMode.MEMORY, [], 2, ["-1"]),
        (CueMode.HOTCUES, ["0", "1"], 0, ["2"]),  # loop takes the first free hot cue slot
    ],
)
def test_cue_modes(
    library: Library,
    tmp_path: Path,
    mode: CueMode,
    hot: list[str],
    memory: int,
    loop_nums: list[str],
) -> None:
    out = tmp_path / "out.xml"
    convert(["House"], library.serato, out, ConvertOptions(cue_mode=mode))
    assert validate_file(out) == []
    marks = list(_tracks_by_name(out)["Opener (DB)"].iterfind("POSITION_MARK"))
    cues = [m for m in marks if m.get("Type") == "0"]
    assert [m.get("Num") for m in cues if m.get("Num") != "-1"] == hot
    assert sum(1 for m in cues if m.get("Num") == "-1") == memory
    assert [m.get("Num") for m in marks if m.get("Type") == "4"] == loop_nums


def test_missing_files_warn_and_continue(library: Library, tmp_path: Path) -> None:
    out = tmp_path / "out.xml"
    report = convert(["Missing"], library.serato, out)
    assert [t.stored_path for t in report.missing] == ["Music/Nowhere/ghost.mp3"]
    assert validate_file(out) == []
    playlist = ET.parse(out).getroot().find("PLAYLISTS/NODE/NODE")
    assert playlist is not None and playlist.get("Entries") == "1"


def test_mp3_fixed_offset(library: Library, tmp_path: Path) -> None:
    out = tmp_path / "out.xml"
    convert(["House"], library.serato, out, ConvertOptions(mp3_offset="26"))
    opener = _tracks_by_name(out)["Opener (DB)"]
    assert [m.get("Start") for m in opener.iterfind("POSITION_MARK")][:1] == ["1.026"]
    tempo = opener.find("TEMPO")
    assert tempo is not None and tempo.get("Inizio") == "0.076"
    cafe = _tracks_by_name(out)["Café Déjà Vu"]  # M4A: never shifted
    assert [m.get("Start") for m in cafe.iterfind("POSITION_MARK")][:1] == ["0.250"]


def test_negative_offset_clamps(library: Library, tmp_path: Path) -> None:
    out = tmp_path / "out.xml"
    report = convert(["House"], library.serato, out, ConvertOptions(mp3_offset=-100))
    assert validate_file(out) == []
    opener = _tracks_by_name(out)["Opener (DB)"]
    tempo = opener.find("TEMPO")
    # 0.05 - 0.1 < 0, so the grid moves forward one beat at 124 BPM
    assert tempo is not None and tempo.get("Inizio") == f"{0.05 - 0.1 + 60 / 124:.3f}"
    assert not any("moved" in w for t in report.tracks for w in t.warnings)


def test_direct_track_paths(library: Library, tmp_path: Path) -> None:
    out = tmp_path / "out.xml"
    flac = library.files["Music/Deep/Low End.flac"]
    report = convert([str(flac)], library.serato, out)
    assert [t.resolved_path for t in report.tracks] == [str(flac)]
    playlist = ET.parse(out).getroot().find("PLAYLISTS/NODE/NODE")
    assert playlist is not None and playlist.get("Name") == "Tracks"


def test_all_crates(library: Library, tmp_path: Path) -> None:
    report = convert([], library.serato, tmp_path / "o.xml", ConvertOptions(all_crates=True))
    assert report.crates == ["House", "House > Deep", "Missing"]
    assert len(report.tracks) == 5  # Opener is shared by House and Missing


def test_unknown_crate(library: Library, tmp_path: Path) -> None:
    with pytest.raises(ConvertError, match="Nothing to convert"):
        convert(["Nope"], library.serato, tmp_path / "o.xml")


def test_refuses_to_write_into_serato_or_audio(library: Library) -> None:
    with pytest.raises(ConvertError, match="inside the Serato folder"):
        convert(["House"], library.serato, library.serato / "out.xml")
    with pytest.raises(ConvertError, match="audio file"):
        convert(["House"], library.serato, library.files["Music/House/Opener.mp3"])


def test_cli_dry_run_json(
    library: Library, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["House%%Deep", "--serato-dir", str(library.serato), "--dry-run", "--json"])
    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["written"] is False and data["crates"] == ["House > Deep"]
    assert {t["format"] for t in data["tracks"]} == {"FLAC", "AIFF"}


def test_cli_requires_output(library: Library, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["House", "--serato-dir", str(library.serato)]) == 2
    assert main(["House", "--serato-dir", str(library.serato), "-n", "--mp3-offset", "x"]) == 2
