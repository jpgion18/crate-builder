from crate_builder.year_genre_log import build_year_genre_csv, summarize_year_genre


def test_builds_csv_with_header_and_rows():
    tracks = [
        {"artist": "Artist A", "title": "Song A", "year": "2015", "genres": "pop, dance pop"},
        {"artist": "Artist B", "title": "Song B", "year": "", "genres": ""},
    ]
    csv_text = build_year_genre_csv(tracks)
    lines = csv_text.strip().splitlines()
    assert lines[0] == "Artist,Title,Year,Genres"
    assert lines[1] == 'Artist A,Song A,2015,"pop, dance pop"'
    assert lines[2] == "Artist B,Song B,,"


def test_handles_commas_in_fields_safely():
    tracks = [{"artist": "Artist, Feat. Someone", "title": "Song, Pt. 1", "year": "2020", "genres": "indie pop"}]
    csv_text = build_year_genre_csv(tracks)
    lines = csv_text.strip().splitlines()
    assert '"Artist, Feat. Someone"' in lines[1]
    assert '"Song, Pt. 1"' in lines[1]


def test_summarize_buckets_by_decade():
    tracks = [
        {"artist": "A", "title": "1", "year": "2015", "genres": ""},
        {"artist": "B", "title": "2", "year": "2018", "genres": ""},
        {"artist": "C", "title": "3", "year": "2021", "genres": ""},
    ]
    result = summarize_year_genre(tracks)
    assert result["by_decade"] == [("2010s", 2), ("2020s", 1)]


def test_summarize_splits_multi_genre_tracks_into_each_bucket():
    # A track whose artist has multiple genre tags counts toward every one
    # of them, not one combined bucket for the joined string.
    tracks = [
        {"artist": "A", "title": "1", "year": "2015", "genres": "pop, dance pop"},
        {"artist": "B", "title": "2", "year": "2016", "genres": "pop"},
    ]
    result = summarize_year_genre(tracks)
    assert dict(result["by_genre"]) == {"pop": 2, "dance pop": 1}


def test_summarize_missing_year_or_genre_counts_as_unknown():
    tracks = [
        {"artist": "A", "title": "1", "year": "", "genres": ""},
        {"artist": "B", "title": "2", "year": "not-a-year", "genres": ""},
    ]
    result = summarize_year_genre(tracks)
    assert result["by_decade"] == [("Unknown", 2)]
    assert result["by_genre"] == [("Unknown", 2)]


def test_summarize_sorts_biggest_bucket_first_ties_alphabetical():
    tracks = [
        {"artist": "A", "title": "1", "year": "2015", "genres": "house"},
        {"artist": "B", "title": "2", "year": "2016", "genres": "pop"},
        {"artist": "C", "title": "3", "year": "2017", "genres": "pop"},
    ]
    result = summarize_year_genre(tracks)
    assert result["by_genre"] == [("pop", 2), ("house", 1)]


def test_summarize_empty_tracks_list():
    assert summarize_year_genre([]) == {"by_decade": [], "by_genre": []}
