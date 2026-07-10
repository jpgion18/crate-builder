from crate_builder.input_parser import InputTrack
from crate_builder.library import Track
from crate_builder.matcher import match_tracks


def make_library():
    return [
        Track(path="/music/a.mp3", title="One More Time", artist="Daft Punk"),
        Track(path="/music/b.mp3", title="Porcelain", artist="Moby"),
        Track(path="/music/c.mp3", title="Around the World", artist="Daft Punk"),
    ]


def test_exact_match():
    library = make_library()
    inputs = [InputTrack(artist="Daft Punk", title="One More Time", raw="Daft Punk - One More Time")]
    results = match_tracks(inputs, library)
    assert results[0].matched is True
    assert results[0].track.path == "/music/a.mp3"


def test_fuzzy_match_handles_typos_and_noise():
    library = make_library()
    inputs = [
        InputTrack(
            artist="Daft Punk",
            title="One More Time (Official Audio)",
            raw="Daft Punk - One More Time (Official Audio)",
        )
    ]
    results = match_tracks(inputs, library)
    assert results[0].matched is True
    assert results[0].track.path == "/music/a.mp3"


def test_no_match_below_threshold():
    library = make_library()
    inputs = [InputTrack(artist="Some Random Band", title="Totally Different Song", raw="x")]
    results = match_tracks(inputs, library, threshold=75)
    assert results[0].matched is False


def test_empty_library_returns_all_unmatched():
    inputs = [InputTrack(artist="Daft Punk", title="One More Time", raw="x")]
    results = match_tracks(inputs, [])
    assert results[0].matched is False
    assert results[0].track is None
