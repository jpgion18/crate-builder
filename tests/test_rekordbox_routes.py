"""The Rekordbox tab's routes and Build Crate's "Also export to Rekordbox", end to end."""

from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from seratobox_fixtures import Library

from app import app
from crate_builder.seratobox.rekordbox import validate_tree


@pytest.fixture
def client():
    app.config["TESTING"] = True
    return app.test_client()


def _snapshot(root: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def _export(client, library: Library, crates: list[str], **extra: str):
    form = {"serato_dir": str(library.serato), "crates_json": json.dumps(crates), **extra}
    return client.post("/api/rekordbox/export", data=form)


@pytest.mark.parametrize("page", ["/", "/discover", "/community", "/library", "/myevents", "/settings", "/rekordbox"])
def test_every_page_links_to_the_tab(client, page: str) -> None:
    html = client.get(page).get_data(as_text=True)
    assert 'href="/rekordbox"' in html


def test_page_has_help(client) -> None:
    html = client.get("/rekordbox").get_data(as_text=True)
    assert "Rekordbox Export" in html and 'id="rb_help_btn"' in html and "Import Playlist" in html


def test_crates_tree(client, library: Library) -> None:
    data = client.get(f"/api/rekordbox/crates?serato_dir={library.serato}").get_json()
    assert data["count"] == 3
    house, missing = data["crates"]
    assert (house["name"], house["ref"], house["track_count"]) == ("House", "House", 2)
    assert house["children"][0]["ref"] == "House%%Deep"
    assert missing["ref"] == "Missing"


def test_crates_bad_folder(client, tmp_path: Path) -> None:
    res = client.get(f"/api/rekordbox/crates?serato_dir={tmp_path / 'nope'}")
    assert res.status_code == 400 and "not found" in res.get_json()["error"]


def test_preview_writes_nothing(client, library: Library) -> None:
    before = _snapshot(library.drive)
    res = client.post(
        "/api/rekordbox/preview",
        json={"serato_dir": str(library.serato), "crates": ["House", "House%%Deep"], "mp3_offset": 26},
    )
    data = res.get_json()
    assert res.status_code == 200, data
    assert data["report"]["written"] is False
    assert len(data["report"]["tracks"]) == 4
    assert "SeratoBox report" in data["text"]
    assert _snapshot(library.drive) == before


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"crates": ["House"]}, "Serato folder"),
        ({"serato_dir": "SERATO"}, "Tick at least one crate"),
        ({"serato_dir": "SERATO", "crates": ["House"], "cue_mode": "nope"}, "cue mode"),
        ({"serato_dir": "SERATO", "crates": ["House"], "mp3_offset": "lots"}, "mp3_offset"),
        ({"serato_dir": "SERATO", "crates": ["Nope"]}, "Nothing to convert"),
    ],
)
def test_preview_errors(client, library: Library, body: dict, message: str) -> None:
    if body.get("serato_dir") == "SERATO":
        body = {**body, "serato_dir": str(library.serato)}
    res = client.post("/api/rekordbox/preview", json=body)
    assert res.status_code == 400 and message in res.get_json()["error"]


def test_export_downloads_valid_xml(client, library: Library) -> None:
    before = _snapshot(library.drive)
    res = _export(client, library, ["House", "House%%Deep"], cue_mode="memory")
    assert res.status_code == 200
    assert res.mimetype == "application/octet-stream"
    assert 'attachment; filename="House (Rekordbox).xml"' in res.headers["Content-Disposition"]
    root = ET.fromstring(res.get_data())
    assert validate_tree(root) == []
    assert len(root.findall("COLLECTION/TRACK")) == 4
    hot = [m for m in root.iter("POSITION_MARK") if m.get("Num") not in ("-1", None)]
    assert hot == []  # memory-only cue mode
    assert _snapshot(library.drive) == before


def test_export_rejects_bad_request(client, library: Library) -> None:
    assert _export(client, library, []).status_code == 400


def test_build_crate_then_export(client, library: Library) -> None:
    """Build Crate's checkbox: build a crate with Crate Builder's own writer, then export it."""
    tracks = [str(library.files["Music/House/Opener.mp3"]), str(library.files["Music/Deep/Low End.flac"])]
    build = client.post(
        "/api/build",
        json={"serato_dir": str(library.serato), "crate_name": "Gigs > Friday", "track_paths": tracks},
    ).get_json()
    assert build["crate_ref"] == "Gigs%%Friday"

    res = _export(client, library, [build["crate_ref"]])
    assert res.status_code == 200
    assert 'filename="Friday (Rekordbox).xml"' in res.headers["Content-Disposition"]
    root = ET.fromstring(res.get_data())
    assert validate_tree(root) == []
    names = {t.get("Name") for t in root.iter("TRACK") if t.get("Name")}
    assert names == {"Opener (DB)", "Low End"}
    playlist = root.find("PLAYLISTS/NODE/NODE/NODE")
    assert playlist is not None and (playlist.get("Name"), playlist.get("Entries")) == ("Friday", "2")


def _build_rekordbox(client, tracks: list[dict], name: str = "Gigs > Friday", target: str = "rekordbox"):
    form = {"crate_name": name, "target": target, "tracks_json": json.dumps(tracks)}
    return client.post("/api/build/rekordbox", data=form)


def test_build_rekordbox_playlist_without_serato(client, library: Library) -> None:
    from crate_builder import local_config

    before = _snapshot(library.drive)
    tracks = [
        {"path": str(library.files["Music/House/Opener.mp3"]), "title": "Opener", "artist": "DJ Test"},
        {"path": str(library.files["Music/Deep/Warehouse.aiff"]), "title": "Warehouse (scan)", "artist": ""},
    ]
    res = _build_rekordbox(client, tracks)
    assert res.status_code == 200, res.get_data(as_text=True)
    assert 'filename="Friday (Rekordbox).xml"' in res.headers["Content-Disposition"]
    root = ET.fromstring(res.get_data())
    assert validate_tree(root) == []
    assert [t.get("Name") for t in root.iterfind("COLLECTION/TRACK")] == ["Opener", "Warehouse (scan)"]
    playlist = root.find("PLAYLISTS/NODE/NODE/NODE")
    assert (playlist.get("Name"), playlist.get("Entries")) == ("Friday", "2")
    assert local_config.get_preference("build_target", "serato") == "rekordbox"
    assert _snapshot(library.drive) == before  # nothing written into the library or Serato


@pytest.mark.parametrize(
    ("name", "tracks", "message"),
    [("", [{"path": "/x.mp3"}], "crate name"), ("X", [], "No tracks"), ("X", [{"title": "no path"}], "No tracks")],
)
def test_build_rekordbox_rejects_bad_requests(client, name: str, tracks: list, message: str) -> None:
    res = _build_rekordbox(client, tracks, name=name)
    assert res.status_code == 400 and message in res.get_json()["error"]


def test_build_target_remembered_and_preselected(client, library: Library) -> None:
    from crate_builder import local_config

    tracks = [str(library.files["Music/House/Opener.mp3"])]
    client.post(
        "/api/build",
        json={"serato_dir": str(library.serato), "crate_name": "Both", "track_paths": tracks, "target": "both"},
    )
    assert local_config.get_preference("build_target", "serato") == "both"
    html = client.get("/").get_data(as_text=True)
    assert '<option value="both" selected>' in html


def test_serato_folder_blank_when_missing(client, monkeypatch, tmp_path: Path) -> None:
    from crate_builder import serato_paths

    monkeypatch.setattr(serato_paths, "guess_serato_dir", lambda: str(tmp_path / "no" / "_Serato_"))
    html = client.get("/").get_data(as_text=True)
    assert 'id="serato_dir" type="text" value=""' in html
