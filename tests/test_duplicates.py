from crate_builder.duplicates import find_duplicates
from crate_builder.library import Track


def test_no_duplicates_in_a_clean_library():
    tracks = [
        Track(path="/a.mp3", title="Song A", artist="Artist A"),
        Track(path="/b.mp3", title="Song B", artist="Artist B"),
    ]
    assert find_duplicates(tracks) == []


def test_exact_duplicate_after_normalization():
    tracks = [
        Track(path="/a1.mp3", title="Song A (Official Audio)", artist="Artist A"),
        Track(path="/a2.flac", title="song a", artist="artist a"),
    ]
    groups = find_duplicates(tracks)
    assert len(groups) == 1
    assert groups[0].reason == "exact"
    assert {t.path for t in groups[0].tracks} == {"/a1.mp3", "/a2.flac"}


def test_fuzzy_duplicate_with_extra_featured_artist_credit():
    tracks = [
        Track(path="/a1.mp3", title="Song A", artist="Artist A"),
        Track(path="/a2.mp3", title="Song A", artist="Artist A feat. Someone"),
    ]
    groups = find_duplicates(tracks, fuzzy_threshold=80)
    assert len(groups) == 1
    assert groups[0].reason == "fuzzy"
    assert {t.path for t in groups[0].tracks} == {"/a1.mp3", "/a2.mp3"}


def test_same_title_different_artist_is_not_a_duplicate():
    tracks = [
        Track(path="/a.mp3", title="Home", artist="Artist A"),
        Track(path="/b.mp3", title="Home", artist="Completely Different Artist"),
    ]
    groups = find_duplicates(tracks)
    assert groups == []


def test_three_way_exact_duplicate_groups_together():
    tracks = [
        Track(path="/a.mp3", title="Song", artist="Artist"),
        Track(path="/b.flac", title="Song", artist="Artist"),
        Track(path="/c.wav", title="Song", artist="Artist"),
    ]
    groups = find_duplicates(tracks)
    assert len(groups) == 1
    assert len(groups[0].tracks) == 3


def test_duplicate_already_counted_as_exact_is_not_also_counted_as_fuzzy():
    tracks = [
        Track(path="/a.mp3", title="Song", artist="Artist"),
        Track(path="/b.mp3", title="Song", artist="Artist"),
    ]
    groups = find_duplicates(tracks)
    assert len(groups) == 1
    assert groups[0].reason == "exact"
