import os

from crate_builder import serato_crate


def test_to_serato_relative_path_strips_leading_slash():
    assert serato_crate.to_serato_relative_path("/Users/dj/Music/song.mp3") == "Users/dj/Music/song.mp3"


def test_build_and_read_round_trip(tmp_path):
    track_paths = [
        str(tmp_path / "Artist A - Song One.mp3"),
        str(tmp_path / "sub" / "Artist B - Song Two.flac"),
    ]
    dest = tmp_path / "Subcrates" / "Test Crate.crate"

    written_path = serato_crate.write_crate(str(dest), track_paths)
    assert os.path.exists(written_path)

    read_paths = serato_crate.read_crate_track_paths(written_path)
    expected = [serato_crate.to_serato_relative_path(p) for p in track_paths]
    assert read_paths == expected


def test_write_crate_refuses_overwrite_by_default(tmp_path):
    dest = tmp_path / "Crate.crate"
    serato_crate.write_crate(str(dest), [str(tmp_path / "a.mp3")])

    try:
        serato_crate.write_crate(str(dest), [str(tmp_path / "b.mp3")])
        assert False, "expected FileExistsError"
    except FileExistsError:
        pass

    serato_crate.write_crate(str(dest), [str(tmp_path / "b.mp3")], overwrite=True)
    assert serato_crate.read_crate_track_paths(str(dest)) == [
        serato_crate.to_serato_relative_path(str(tmp_path / "b.mp3"))
    ]
