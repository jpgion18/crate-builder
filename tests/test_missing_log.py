from crate_builder.missing_log import build_missing_log_csv


def test_builds_csv_with_header_and_rows():
    tracks = [
        {"artist": "Unknown Artist", "title": "Totally Different Song", "raw": "Unknown Artist - Totally Different Song"},
        {"artist": "", "title": "No Artist Track", "raw": "No Artist Track"},
    ]
    csv_text = build_missing_log_csv(tracks)
    lines = csv_text.strip().splitlines()
    assert lines[0] == "Artist,Title,Original Input,Notes"
    assert lines[1] == "Unknown Artist,Totally Different Song,Unknown Artist - Totally Different Song,"
    assert lines[2] == ",No Artist Track,No Artist Track,"


def test_handles_commas_in_fields_safely():
    tracks = [{"artist": "Artist, Feat. Someone", "title": "Song, Pt. 1", "raw": "raw"}]
    csv_text = build_missing_log_csv(tracks)
    lines = csv_text.strip().splitlines()
    assert '"Artist, Feat. Someone"' in lines[1]
    assert '"Song, Pt. 1"' in lines[1]
