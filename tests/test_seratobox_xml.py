"""Rekordbox XML writer and validator."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote, urlparse

from crate_builder.seratobox.rekordbox import (
    RbMark,
    RbNode,
    RbTempo,
    RbTrack,
    build_tree,
    location_uri,
    validate_file,
    validate_tree,
    write_xml,
)


def test_location_encoding_round_trips() -> None:
    path = Path("/Volumes/USB/Música/Café #1 & 50% [VIP]?.mp3")
    uri = location_uri(path)
    assert uri.startswith("file://localhost/Volumes/USB/M%C3%BAsica/")
    assert " " not in uri and "#" not in uri and "?" not in uri and uri.isascii()
    assert unquote(urlparse(uri).path) == str(path)


def _sample() -> tuple[list[RbTrack], list[RbNode]]:
    track = RbTrack(
        track_id=1,
        path=Path("/Music/a & b <c>.mp3"),
        name='Say "hi" & <bye>\x01',
        artist="Ärtist",
        kind="MP3 File",
        average_bpm=128.0,
        tempos=[RbTempo(0.05, 128.0)],
        marks=[
            RbMark(1.0, 0, name="A", rgb=(204, 0, 0)),
            RbMark(1.0, -1, name="A"),
            RbMark(2.0, -1, type=4, end_s=4.5, name="L"),
        ],
    )
    nodes = [
        RbNode("House", children=[RbNode("House", track_ids=[1]), RbNode("Deep", track_ids=[1])])
    ]
    return [track], nodes


def test_written_xml_is_valid_and_readable(tmp_path: Path) -> None:
    tracks, nodes = _sample()
    out = tmp_path / "out.xml"
    write_xml(tracks, nodes, out)
    assert out.read_bytes().startswith(b"<?xml version='1.0' encoding='UTF-8'?>")
    assert validate_file(out) == []
    root = ET.parse(out).getroot()
    track = root.find("COLLECTION/TRACK")
    assert track is not None
    assert track.get("Name") == 'Say "hi" & <bye>'  # control char stripped, rest escaped
    marks = track.findall("POSITION_MARK")
    assert [(m.get("Type"), m.get("Num"), m.get("Start"), m.get("End")) for m in marks] == [
        ("0", "0", "1.000", None),
        ("0", "-1", "1.000", None),
        ("4", "-1", "2.000", "4.500"),
    ]
    assert marks[0].get("Red") == "204" and marks[1].get("Red") is None
    tempo = track.find("TEMPO")
    assert tempo is not None and tempo.attrib == {
        "Inizio": "0.050",
        "Bpm": "128.00",
        "Metro": "4/4",
        "Battito": "1",
    }
    folder = root.find("PLAYLISTS/NODE/NODE")
    assert folder is not None and folder.get("Type") == "0" and folder.get("Count") == "2"


def test_no_temp_files_left(tmp_path: Path) -> None:
    tracks, nodes = _sample()
    write_xml(tracks, nodes, tmp_path / "out.xml")
    assert [p.name for p in tmp_path.iterdir()] == ["out.xml"]


def test_validator_catches_problems() -> None:
    tracks, nodes = _sample()
    root = build_tree(tracks, nodes).getroot()
    track = root.find("COLLECTION/TRACK")
    assert track is not None
    track.set("Location", "file://localhost/has space.mp3")
    ET.SubElement(track, "POSITION_MARK", Name="", Type="0", Start="3", Num="0")
    ET.SubElement(track, "POSITION_MARK", Name="", Type="4", Start="3", End="2", Num="-1")
    playlist = root.find("PLAYLISTS/NODE/NODE/NODE")
    assert playlist is not None
    ET.SubElement(playlist, "TRACK", Key="99")
    errors = validate_tree(root)
    assert any("percent-encoded" in e for e in errors)
    assert any("two hot cues in slot 0" in e for e in errors)
    assert any("invalid End" in e for e in errors)
    assert any("unknown TrackID 99" in e for e in errors)
    assert any("Entries=1 but has 2" in e for e in errors)


def test_validator_rejects_malformed_file(tmp_path: Path) -> None:
    bad = tmp_path / "bad.xml"
    bad.write_text("<DJ_PLAYLISTS><COLLECTION>")
    assert validate_file(bad)[0].startswith("not well-formed")
