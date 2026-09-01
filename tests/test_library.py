from crate_builder.library import Track, apply_serato_metadata
from crate_builder.serato_database import SeratoDbTrack


def test_serato_metadata_overrides_scanned_tags():
    tracks = [Track(path="/music/a.mp3", title="filename guess", artist="")]
    serato_tracks = [SeratoDbTrack(path="/music/a.mp3", title="One More Time", artist="Daft Punk")]
    result = apply_serato_metadata(tracks, serato_tracks)
    assert result[0].title == "One More Time"
    assert result[0].artist == "Daft Punk"
    assert result[0].search_key == "daft punk one more time"


def test_no_serato_entry_leaves_scanned_tags_untouched():
    tracks = [Track(path="/music/a.mp3", title="Original Title", artist="Original Artist")]
    result = apply_serato_metadata(tracks, [SeratoDbTrack(path="/music/other.mp3", title="X", artist="Y")])
    assert result[0].title == "Original Title"
    assert result[0].artist == "Original Artist"


def test_empty_serato_field_does_not_overwrite():
    tracks = [Track(path="/music/a.mp3", title="Kept Title", artist="Kept Artist")]
    serato_tracks = [SeratoDbTrack(path="/music/a.mp3", title="", artist="")]
    result = apply_serato_metadata(tracks, serato_tracks)
    assert result[0].title == "Kept Title"
    assert result[0].artist == "Kept Artist"


def test_path_matching_normalizes_redundant_separators():
    tracks = [Track(path="/music//a.mp3", title="Original", artist="Original")]
    serato_tracks = [SeratoDbTrack(path="/music/a.mp3", title="Fixed", artist="Fixed")]
    result = apply_serato_metadata(tracks, serato_tracks)
    assert result[0].title == "Fixed"
    assert result[0].artist == "Fixed"
