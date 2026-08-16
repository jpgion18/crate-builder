from crate_builder.input_parser import InputTrack, parse_input_text


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


def test_parses_title_by_artist_when_no_dash_separator():
    text = "One More Time by Daft Punk\nPorcelain by Moby"
    tracks = parse_input_text(text)
    assert [(t.artist, t.title) for t in tracks] == [
        ("Daft Punk", "One More Time"),
        ("Moby", "Porcelain"),
    ]


def test_dash_separator_takes_priority_over_by():
    # "by" appears in the title itself — the dash split should win, not "by".
    text = "Daft Punk - Around the World (Stardust Duty Free Remix by DJ X)"
    tracks = parse_input_text(text)
    assert tracks[0].artist == "Daft Punk"
    assert tracks[0].title == "Around the World (Stardust Duty Free Remix by DJ X)"


def test_strips_trailing_mix_timestamps():
    text = "Daft Punk - One More Time [03:14]\nMoby - Porcelain (3:14)"
    tracks = parse_input_text(text)
    assert [(t.artist, t.title) for t in tracks] == [
        ("Daft Punk", "One More Time"),
        ("Moby", "Porcelain"),
    ]


def test_strips_leading_bullet_characters():
    text = "- Daft Punk - One More Time\n• Moby - Porcelain\n* Air - La Femme d'Argent"
    tracks = parse_input_text(text)
    assert [(t.artist, t.title) for t in tracks] == [
        ("Daft Punk", "One More Time"),
        ("Moby", "Porcelain"),
        ("Air", "La Femme d'Argent"),
    ]


def test_numbered_and_bulleted_line_combined():
    text = "1) - Daft Punk - One More Time"
    tracks = parse_input_text(text)
    assert tracks == [InputTrack(artist="Daft Punk", title="One More Time", raw="1) - Daft Punk - One More Time")]


def test_raw_preserves_the_original_unstripped_line():
    text = "03. Daft Punk - One More Time [03:14]"
    tracks = parse_input_text(text)
    assert tracks[0].raw == "03. Daft Punk - One More Time [03:14]"
