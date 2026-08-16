import struct

import pytest

from crate_builder import yearcheck_runner, yearcheck_store
from crate_builder.serato_database import SeratoDbTrack


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setattr(yearcheck_store, "STORE_PATH", str(tmp_path / "year_check_results.json"))
    yearcheck_runner._state.update({"status": "idle", "total": 0, "checked": 0, "current": ""})
    yearcheck_runner._stop_requested = False
    yield
    yearcheck_runner._state.update({"status": "idle", "total": 0, "checked": 0, "current": ""})
    yearcheck_runner._stop_requested = False


def test_initial_status_is_idle():
    assert yearcheck_runner.get_status()["status"] == "idle"


def test_start_propagates_missing_database_error():
    with pytest.raises(Exception):
        yearcheck_runner.start("/no/such/database V2")


def test_start_raises_when_already_running():
    yearcheck_runner._state["status"] = "running"
    with pytest.raises(yearcheck_runner.YearCheckError):
        yearcheck_runner.start("/no/such/database V2")


def test_run_processes_tracks_and_saves_results(monkeypatch):
    monkeypatch.setattr(yearcheck_runner.time, "sleep", lambda s: None)
    monkeypatch.setattr(
        yearcheck_runner.musicbrainz_client,
        "lookup_year",
        lambda artist, title: {
            "status": "matched", "mb_year": "2019", "score": 100, "mb_link": "x", "candidates": [], "note": "",
        },
    )
    tracks = [
        SeratoDbTrack(path="/a.mp3", title="Song A", artist="Artist A", year="2019"),
        SeratoDbTrack(path="/b.mp3", title="Song B", artist="Artist B", year="2015"),
    ]
    yearcheck_runner._state["status"] = "running"
    yearcheck_runner._state["total"] = len(tracks)
    yearcheck_runner._run(tracks)

    results = {r["title"]: r for r in yearcheck_store.get_cached_results()}
    assert len(results) == 2
    assert results["Song A"]["status"] == "match"  # tag_year "2019" == mb_year "2019"
    assert results["Song B"]["status"] == "mismatch"  # tag_year "2015" != mb_year "2019"
    status = yearcheck_runner.get_status()
    assert status["status"] == "idle"
    assert status["checked"] == 2


def test_stop_halts_the_batch_early(monkeypatch):
    monkeypatch.setattr(yearcheck_runner.time, "sleep", lambda s: None)
    call_count = {"n": 0}

    def fake_lookup(artist, title):
        call_count["n"] += 1
        if call_count["n"] == 1:
            yearcheck_runner.stop()
        return {"status": "notfound", "mb_year": None, "score": None, "mb_link": None, "candidates": [], "note": ""}

    monkeypatch.setattr(yearcheck_runner.musicbrainz_client, "lookup_year", fake_lookup)
    tracks = [
        SeratoDbTrack(path="/a.mp3", title="Song A", artist="Artist A"),
        SeratoDbTrack(path="/b.mp3", title="Song B", artist="Artist B"),
        SeratoDbTrack(path="/c.mp3", title="Song C", artist="Artist C"),
    ]
    yearcheck_runner._run(tracks)

    status = yearcheck_runner.get_status()
    assert status["status"] == "stopped"
    assert status["checked"] == 1


def _build_database_file(tmp_path, tracks: list[dict]) -> str:
    def chunk(tag: str, payload: bytes) -> bytes:
        return tag.encode("ascii") + struct.pack(">I", len(payload)) + payload

    def text(s: str) -> bytes:
        return s.encode("utf-16-be")

    def track_chunk(fields: dict) -> bytes:
        return chunk("otrk", b"".join(chunk(t, text(v)) for t, v in fields.items()))

    data = b"".join(track_chunk(t) for t in tracks)
    path = tmp_path / "database V2"
    path.write_bytes(data)
    return str(path)


def test_start_skips_already_checked_tracks(tmp_path, monkeypatch):
    yearcheck_store.save_result("Artist A", "Song A", {"status": "match"})
    db_path = _build_database_file(
        tmp_path,
        [{"tsng": "Song A", "tart": "Artist A"}, {"tsng": "Song B", "tart": "Artist B"}],
    )

    # Don't actually spawn/run the background thread — only start()'s
    # synchronous filtering-and-setup behavior is under test here.
    monkeypatch.setattr(
        yearcheck_runner.threading,
        "Thread",
        lambda target, args, daemon: type("FakeThread", (), {"start": lambda self: None})(),
    )

    yearcheck_runner.start(db_path)

    assert yearcheck_runner.get_status()["total"] == 1  # Song A already checked, only Song B left


def test_start_respects_limit(tmp_path, monkeypatch):
    db_path = _build_database_file(
        tmp_path,
        [{"tsng": "Song A", "tart": "Artist A"}, {"tsng": "Song B", "tart": "Artist B"}],
    )
    monkeypatch.setattr(
        yearcheck_runner.threading,
        "Thread",
        lambda target, args, daemon: type("FakeThread", (), {"start": lambda self: None})(),
    )

    yearcheck_runner.start(db_path, limit=1)

    assert yearcheck_runner.get_status()["total"] == 1
