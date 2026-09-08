from crate_builder.year_genre_log import build_year_genre_csv


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
