import struct

import pytest

from crate_builder import serato_database


def _chunk(tag: str, payload: bytes) -> bytes:
    return tag.encode("ascii") + struct.pack(">I", len(payload)) + payload


def _text(s: str) -> bytes:
    return s.encode("utf-16-be")


def _u32(n: int) -> bytes:
    return struct.pack(">I", n)


def _build_track_chunk(fields: dict) -> bytes:
    payload = b""
    for tag, value in fields.items():
        if isinstance(value, str):
            payload += _chunk(tag, _text(value))
        elif isinstance(value, int):
            payload += _chunk(tag, _u32(value))
        else:
            raise TypeError(f"unsupported test field type for {tag!r}")
    return _chunk("otrk", payload)


def _build_database(tracks: list[dict]) -> bytes:
    return b"".join(_build_track_chunk(fields) for fields in tracks)


@pytest.fixture
def db_file(tmp_path):
    def _write(tracks: list[dict]) -> str:
        path = tmp_path / "database V2"
        path.write_bytes(_build_database(tracks))
        return str(path)

    return _write


def test_missing_file_raises():
    with pytest.raises(serato_database.SeratoDatabaseError):
        serato_database.parse_database("/no/such/database V2")


def test_parses_basic_fields(db_file):
    path = db_file(
        [
            {"pfil": "Users/dj/Music/song.mp3", "tsng": "Song One", "tart": "Artist A", "talb": "Album A", "ttyr": "2019"},
        ]
    )
    tracks = serato_database.parse_database(path)
    assert len(tracks) == 1
    t = tracks[0]
    assert t.path == "/Users/dj/Music/song.mp3"
    assert t.title == "Song One"
    assert t.artist == "Artist A"
    assert t.album == "Album A"
    assert t.year == "2019"


def test_parses_energy_from_comment(db_file):
    path = db_file([{"tsng": "Song", "tart": "Artist", "tcom": "Energy 7 - some other note"}])
    tracks = serato_database.parse_database(path)
    assert tracks[0].energy == 7


def test_missing_energy_comment_is_none(db_file):
    path = db_file([{"tsng": "Song", "tart": "Artist", "tcom": "just a note"}])
    assert serato_database.parse_database(path)[0].energy is None


def test_source_falls_back_from_tcmp_to_trmx(db_file):
    path = db_file([{"tsng": "Song", "tart": "Artist", "trmx": "BPM Supreme"}])
    assert serato_database.parse_database(path)[0].source == "BPM Supreme"

    path2 = db_file([{"tsng": "Song", "tart": "Artist", "tcmp": "Central", "trmx": "BPM Supreme"}])
    assert serato_database.parse_database(path2)[0].source == "Central"


def test_multiple_tracks_parsed_in_order(db_file):
    path = db_file(
        [
            {"tsng": "First", "tart": "Artist"},
            {"tsng": "Second", "tart": "Artist"},
        ]
    )
    tracks = serato_database.parse_database(path)
    assert [t.title for t in tracks] == ["First", "Second"]


def test_non_otrk_top_level_chunks_are_ignored(tmp_path):
    data = _chunk("vrsn", _text("2.0/Serato Scratch LIVE Database")) + _build_track_chunk({"tsng": "Song", "tart": "Artist"})
    path = tmp_path / "database V2"
    path.write_bytes(data)
    tracks = serato_database.parse_database(str(path))
    assert len(tracks) == 1
    assert tracks[0].title == "Song"


def test_missing_fields_default_to_empty():
    from crate_builder.serato_database import _to_track

    t = _to_track({})
    assert t.path == ""
    assert t.title == ""
    assert t.artist == ""
    assert t.energy is None


class TestResolveSeratoPath:
    def test_empty_string(self):
        assert serato_database.resolve_serato_path("") == ""

    def test_prepends_slash_for_posix_relative_path(self, monkeypatch):
        monkeypatch.setattr(serato_database, "is_windows", lambda: False)
        assert serato_database.resolve_serato_path("Users/dj/Music/song.mp3") == "/Users/dj/Music/song.mp3"

    def test_leaves_windows_drive_path_untouched(self, monkeypatch):
        monkeypatch.setattr(serato_database, "is_windows", lambda: False)
        assert serato_database.resolve_serato_path("C:/Users/dj/Music/song.mp3") == "C:/Users/dj/Music/song.mp3"

    def test_leaves_already_absolute_path_untouched(self, monkeypatch):
        monkeypatch.setattr(serato_database, "is_windows", lambda: False)
        assert serato_database.resolve_serato_path("/Users/dj/Music/song.mp3") == "/Users/dj/Music/song.mp3"
