from unittest.mock import Mock, patch

from crate_builder import musicbrainz_client


def test_clean_title_for_search_strips_pool_edit_descriptors():
    assert musicbrainz_client.clean_title_for_search("Song (Clean Extended)") == "Song"
    assert musicbrainz_client.clean_title_for_search("Song (Radio Edit)") == "Song"


def test_clean_title_for_search_keeps_genuine_remix_names():
    assert musicbrainz_client.clean_title_for_search("Song (R3HAB Remix)") == "Song (R3HAB Remix)"


def test_primary_artist_strips_featured_credits():
    assert musicbrainz_client.primary_artist("Artist A ft. Artist B") == "Artist A"
    assert musicbrainz_client.primary_artist("Artist A feat Artist B") == "Artist A"
    assert musicbrainz_client.primary_artist("Artist A, Artist B") == "Artist A"
    assert musicbrainz_client.primary_artist("Artist A & Artist B") == "Artist A"
    assert musicbrainz_client.primary_artist("Artist A vs Artist B") == "Artist A"


def _mock_response(recordings):
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.json.return_value = {"recordings": recordings}
    return resp


def test_matched_when_score_high_and_year_present():
    recordings = [{"id": "abc", "score": 100, "first-release-date": "2019-05-01"}]
    with patch("crate_builder.musicbrainz_client.requests.get", return_value=_mock_response(recordings)):
        result = musicbrainz_client.lookup_year("Artist A", "Song One")
    assert result["status"] == "matched"
    assert result["mb_year"] == "2019"
    assert result["score"] == 100
    assert len(result["candidates"]) == 1


def test_notfound_when_no_recordings():
    with patch("crate_builder.musicbrainz_client.requests.get", return_value=_mock_response([])):
        result = musicbrainz_client.lookup_year("Artist A", "Song One")
    assert result["status"] == "notfound"
    assert result["mb_year"] is None


def test_notfound_when_score_below_threshold():
    recordings = [{"id": "abc", "score": 50, "first-release-date": "2019-05-01"}]
    with patch("crate_builder.musicbrainz_client.requests.get", return_value=_mock_response(recordings)):
        result = musicbrainz_client.lookup_year("Artist A", "Song One")
    assert result["status"] == "notfound"
    assert "too weak" in result["note"]


def test_notfound_when_matched_but_no_release_date():
    recordings = [{"id": "abc", "score": 100}]
    with patch("crate_builder.musicbrainz_client.requests.get", return_value=_mock_response(recordings)):
        result = musicbrainz_client.lookup_year("Artist A", "Song One")
    assert result["status"] == "notfound"
    assert "no release date" in result["note"]


def test_returns_up_to_three_candidates_not_just_the_best():
    recordings = [
        {"id": "a", "score": 100, "first-release-date": "2019-05-01"},
        {"id": "b", "score": 90, "first-release-date": "2015-01-01"},
        {"id": "c", "score": 85, "first-release-date": "2010-01-01"},
        {"id": "d", "score": 80, "first-release-date": "2008-01-01"},
    ]
    with patch("crate_builder.musicbrainz_client.requests.get", return_value=_mock_response(recordings)):
        result = musicbrainz_client.lookup_year("Artist A", "Song One")
    assert len(result["candidates"]) == 3


def test_error_on_request_failure():
    with patch("crate_builder.musicbrainz_client.requests.get", side_effect=Exception("boom")):
        result = musicbrainz_client.lookup_year("Artist A", "Song One")
    assert result["status"] == "error"
    assert "boom" in result["note"]


def test_sends_expected_query_and_user_agent():
    with patch("crate_builder.musicbrainz_client.requests.get", return_value=_mock_response([])) as mock_get:
        musicbrainz_client.lookup_year("Artist A ft. Artist B", "Song (Radio Edit)")

    _, kwargs = mock_get.call_args
    assert kwargs["params"]["query"] == 'recording:"Song" AND artist:"Artist A"'
    assert kwargs["headers"]["User-Agent"] == musicbrainz_client.USER_AGENT
