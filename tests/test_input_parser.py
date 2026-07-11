from crate_builder.input_parser import parse_input_text


def test_parses_plain_artist_title_lines():
    text = "Daft Punk - One More Time\nMoby - Porcelain"
    tracks = parse_input_text(text)
    assert [(t.artist, t.title) for t in tracks] == [
        ("Daft Punk", "One More Time"),
        ("Moby", "Porcelain"),
    ]


def test_parses_title_only_lines():
    text = "One More Time\nPorcelain"
    tracks = parse_input_text(text)
    assert [t.title for t in tracks] == ["One More Time", "Porcelain"]
    assert all(t.artist == "" for t in tracks)


def test_parses_csv_with_header():
    text = 'Track Name,Artist Name(s)\n"One More Time","Daft Punk"\n"Porcelain","Moby"'
    tracks = parse_input_text(text)
    assert [(t.artist, t.title) for t in tracks] == [
        ("Daft Punk", "One More Time"),
        ("Moby", "Porcelain"),
    ]


def test_parses_csv_with_alternate_header_names():
    text = 'Song Title,Artist Name\n"One More Time","Daft Punk"\n"Porcelain","Moby"'
    tracks = parse_input_text(text)
    assert [(t.artist, t.title) for t in tracks] == [
        ("Daft Punk", "One More Time"),
        ("Moby", "Porcelain"),
    ]


def test_parses_headerless_csv_as_artist_title():
    text = "Daft Punk,One More Time\nMoby,Porcelain"
    tracks = parse_input_text(text)
    assert [(t.artist, t.title) for t in tracks] == [
        ("Daft Punk", "One More Time"),
        ("Moby", "Porcelain"),
    ]


def test_ignores_blank_lines():
    text = "Daft Punk - One More Time\n\n\nMoby - Porcelain\n"
    tracks = parse_input_text(text)
    assert len(tracks) == 2


def test_empty_input_returns_empty_list():
    assert parse_input_text("   \n  ") == []
