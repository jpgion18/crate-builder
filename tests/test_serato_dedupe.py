import os
import struct

import pytest

from crate_builder import serato_dedupe
from crate_builder.serato_crate import read_crate_track_paths, to_serato_relative_path
from crate_builder.serato_dedupe import DedupeError, RemovalPlan
from crate_builder.serato_database import parse_database


def _chunk(tag: str, payload: bytes) -> bytes:
    return tag.encode("ascii") + struct.pack(">I", len(payload)) + payload


def _text(s: str) -> bytes:
    return s.encode("utf-16-be")


def _db_track(path: str, artist: str, title: str, extra: bytes = b"") -> bytes:
    rel = to_serato_relative_path(path)
    payload = _chunk("pfil", _text(rel)) + _chunk("tart", _text(artist)) + _chunk("tsng", _text(title)) + extra
    return _chunk("otrk", payload)


def _crate(paths: list[str]) -> bytes:
    out = _chunk("vrsn", _text("1.0/Serato ScratchLive Crate"))
    out += _chunk("osrt", _chunk("tvcn", _text("song")))  # a sort column, must survive untouched
    for p in paths:
        out += _chunk("otrk", _chunk("ptrk", _text(to_serato_relative_path(p))))
    return out


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(serato_dedupe, "_BACKUP_ROOT", str(tmp_path / "backups"))
    monkeypatch.setattr(serato_dedupe, "_REMOVED_ROOT", str(tmp_path / "removed"))
    monkeypatch.setattr(serato_dedupe, "serato_is_running", lambda: False)

    music = tmp_path / "Music"
    music.mkdir()
    a1 = music / "Artist - Song.mp3"
    a2 = music / "dupes" / "Artist - Song.flac"
    b = music / "Other - Tune.mp3"
    a2.parent.mkdir()
    a1.write_bytes(b"mp3")
    a2.write_bytes(b"flac-bigger")
    b.write_bytes(b"other")

    serato = tmp_path / "_Serato_"
    (serato / "Subcrates").mkdir(parents=True)
    cue_blob = _chunk("bhrt", b"\x01")  # stand-in for fields we don't decode
    db = _chunk("vrsn", _text("2.0/Serato Scratch LIVE Database"))
    db += _db_track(str(a1), "Artist", "Song", cue_blob)
    db += _db_track(str(a2), "Artist", "Song")
    db += _db_track(str(b), "Other", "Tune")
    (serato / "database V2").write_bytes(db)
    (serato / "Subcrates" / "House.crate").write_bytes(_crate([str(a2), str(b)]))
    (serato / "Subcrates" / "Both.crate").write_bytes(_crate([str(a1), str(a2)]))
    (serato / "Subcrates" / "Clean.crate").write_bytes(_crate([str(b)]))

    return {"serato": str(serato), "a1": str(a1), "a2": str(a2), "b": str(b), "db": db, "tmp": tmp_path}


def test_removes_track_repoints_crates_and_moves_file(setup):
    s = setup
    clean_before = open(os.path.join(s["serato"], "Subcrates", "Clean.crate"), "rb").read()

    result = serato_dedupe.remove_duplicates(s["serato"], [RemovalPlan(keep=s["a1"], remove=[s["a2"]])])

    assert result.removed_from_database == 1
    tracks = parse_database(os.path.join(s["serato"], "database V2"))
    assert sorted(t.path for t in tracks) == sorted([s["a1"], s["b"]])
    # Fields we don't decode on the kept track are untouched.
    assert b"bhrt" in open(os.path.join(s["serato"], "database V2"), "rb").read()

    house = read_crate_track_paths(os.path.join(s["serato"], "Subcrates", "House.crate"))
    assert house == [to_serato_relative_path(s["a1"]), to_serato_relative_path(s["b"])]
    both = read_crate_track_paths(os.path.join(s["serato"], "Subcrates", "Both.crate"))
    assert both == [to_serato_relative_path(s["a1"])]  # no double entry
    assert b"osrt" in open(os.path.join(s["serato"], "Subcrates", "House.crate"), "rb").read()
    assert open(os.path.join(s["serato"], "Subcrates", "Clean.crate"), "rb").read() == clean_before
    assert sorted(result.crates_updated) == ["Both", "House"]

    assert not os.path.exists(s["a2"])
    assert len(result.files_moved) == 1
    assert os.path.isfile(result.files_moved[0]["moved_to"])
    assert result.files_moved[0]["moved_to"].startswith(str(s["tmp"] / "removed"))


def test_keep_file_action_leaves_audio_on_disk(setup):
    s = setup
    result = serato_dedupe.remove_duplicates(
        s["serato"], [RemovalPlan(keep=s["a1"], remove=[s["a2"]])], file_action="keep"
    )
    assert os.path.isfile(s["a2"])
    assert result.files_moved == []


def test_undo_restores_everything(setup):
    s = setup
    crates_before = {
        n: open(os.path.join(s["serato"], "Subcrates", n), "rb").read()
        for n in os.listdir(os.path.join(s["serato"], "Subcrates"))
    }
    result = serato_dedupe.remove_duplicates(s["serato"], [RemovalPlan(keep=s["a1"], remove=[s["a2"]])])

    backups = serato_dedupe.list_serato_backups()
    assert backups[0]["backup_id"] == result.backup_id
    assert backups[0]["removed_count"] == 1

    outcome = serato_dedupe.restore_serato_backup(result.backup_id)
    assert outcome["file_errors"] == []
    assert open(os.path.join(s["serato"], "database V2"), "rb").read() == s["db"]
    for name, data in crates_before.items():
        assert open(os.path.join(s["serato"], "Subcrates", name), "rb").read() == data
    assert open(s["a2"], "rb").read() == b"flac-bigger"
    assert serato_dedupe.list_serato_backups()[0]["restored"] is True


def test_rejects_tracks_that_are_not_duplicates_of_each_other(setup):
    s = setup
    with pytest.raises(DedupeError):
        serato_dedupe.remove_duplicates(s["serato"], [RemovalPlan(keep=s["a1"], remove=[s["b"]])])
    assert open(os.path.join(s["serato"], "database V2"), "rb").read() == s["db"]
    assert not os.path.exists(str(s["tmp"] / "backups"))


def test_rejects_keep_and_remove_same_track(setup):
    s = setup
    with pytest.raises(DedupeError):
        serato_dedupe.remove_duplicates(s["serato"], [RemovalPlan(keep=s["a1"], remove=[s["a1"]])])


def test_rejects_removing_every_copy_across_plans(setup):
    s = setup
    with pytest.raises(DedupeError):
        serato_dedupe.remove_duplicates(
            s["serato"],
            [RemovalPlan(keep=s["a1"], remove=[s["a2"]]), RemovalPlan(keep=s["a2"], remove=[s["a1"]])],
        )


def test_refuses_while_serato_is_running(setup, monkeypatch):
    s = setup
    monkeypatch.setattr(serato_dedupe, "serato_is_running", lambda: True)
    with pytest.raises(DedupeError, match="Quit Serato"):
        serato_dedupe.remove_duplicates(s["serato"], [RemovalPlan(keep=s["a1"], remove=[s["a2"]])])


def test_empty_selection_is_an_error(setup):
    s = setup
    with pytest.raises(DedupeError):
        serato_dedupe.remove_duplicates(s["serato"], [RemovalPlan(keep=s["a1"], remove=[])])


def test_suggest_keep_prefers_existing_then_crates_then_size():
    tracks = [
        {"path": "/gone", "exists": False, "crate_count": 9, "file_size": None},
        {"path": "/small", "exists": True, "crate_count": 2, "file_size": 10},
        {"path": "/big", "exists": True, "crate_count": 2, "file_size": 99},
    ]
    assert serato_dedupe.suggest_keep(tracks) == "/big"


def test_api_scan_and_remove(setup):
    import app as app_module

    s = setup
    client = app_module.app.test_client()
    scan = client.post("/api/duplicates", json={"serato_dir": s["serato"]}).get_json()
    assert len(scan["groups"]) == 1
    group = scan["groups"][0]
    by_path = {t["path"]: t for t in group["tracks"]}
    assert by_path[s["a1"]]["crate_count"] == 1
    assert by_path[s["a2"]]["crate_count"] == 2
    assert group["suggested_keep"] == s["a2"]

    res = client.post(
        "/api/duplicates/remove",
        json={"serato_dir": s["serato"], "file_action": "move", "groups": [{"keep": s["a2"], "remove": [s["a1"]]}]},
    )
    body = res.get_json()
    assert res.status_code == 200, body
    assert body["removed_from_database"] == 1

    undo = client.post("/api/duplicates/undo", json={"backup_id": body["backup_id"]})
    assert undo.status_code == 200
    assert os.path.isfile(s["a1"])


def test_api_undo_rejects_path_traversal(setup):
    import app as app_module

    res = app_module.app.test_client().post("/api/duplicates/undo", json={"backup_id": "../etc"})
    assert res.status_code == 400
