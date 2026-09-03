from unittest.mock import Mock, patch

import pytest
import requests

from crate_builder.link_fetcher import LinkFetchError, fetch_tracklist_text, is_shared_link


def test_is_shared_link_detects_dropbox():
    assert is_shared_link("https://www.dropbox.com/s/abc123/setlist.txt?dl=0") is True


def test_is_shared_link_detects_drive_file():
    assert is_shared_link("https://drive.google.com/file/d/abc123/view?usp=sharing") is True


def test_is_shared_link_detects_google_docs():
    assert is_shared_link("https://docs.google.com/document/d/abc123/edit") is True


def test_is_shared_link_detects_google_sheets():
    assert is_shared_link("https://docs.google.com/spreadsheets/d/abc123/edit") is True


def test_is_shared_link_false_for_plain_text():
    assert is_shared_link("Daft Punk - One More Time") is False


def _mock_response(text: str, content_type: str = "text/plain"):
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.headers = {"Content-Type": content_type}
    resp.content = text.encode("utf-8")
    return resp


def test_dropbox_link_converted_to_direct_download():
    with patch("crate_builder.link_fetcher.requests.get", return_value=_mock_response("Artist - Title")) as mock_get:
        result = fetch_tracklist_text("https://www.dropbox.com/s/abc123/setlist.txt?dl=0")
    assert result == "Artist - Title"
    fetched_url = mock_get.call_args[0][0]
    assert "dl=1" in fetched_url
    assert "dl=0" not in fetched_url


def test_dropbox_link_without_dl_param_gets_one_appended():
    with patch("crate_builder.link_fetcher.requests.get", return_value=_mock_response("Artist - Title")) as mock_get:
        fetch_tracklist_text("https://www.dropbox.com/s/abc123/setlist.txt")
    assert "dl=1" in mock_get.call_args[0][0]


def test_google_docs_link_uses_export_endpoint():
    with patch("crate_builder.link_fetcher.requests.get", return_value=_mock_response("Artist - Title")) as mock_get:
        fetch_tracklist_text("https://docs.google.com/document/d/abc123/edit?usp=sharing")
    assert mock_get.call_args[0][0] == "https://docs.google.com/document/d/abc123/export?format=txt"


def test_google_sheets_link_uses_export_endpoint():
    with patch("crate_builder.link_fetcher.requests.get", return_value=_mock_response("Artist,Title")) as mock_get:
        fetch_tracklist_text("https://docs.google.com/spreadsheets/d/xyz789/edit#gid=0")
    assert mock_get.call_args[0][0] == "https://docs.google.com/spreadsheets/d/xyz789/export?format=csv"


def test_drive_file_link_uses_download_endpoint():
    with patch("crate_builder.link_fetcher.requests.get", return_value=_mock_response("Artist - Title")) as mock_get:
        fetch_tracklist_text("https://drive.google.com/file/d/fileid456/view?usp=sharing")
    assert mock_get.call_args[0][0] == "https://drive.google.com/uc?export=download&id=fileid456"


def test_html_response_raises_a_clear_error():
    with patch("crate_builder.link_fetcher.requests.get", return_value=_mock_response("<html>sign in</html>", "text/html")):
        with pytest.raises(LinkFetchError, match="Anyone with the link"):
            fetch_tracklist_text("https://www.dropbox.com/s/abc123/setlist.txt?dl=0")


def test_non_utf8_content_raises_a_clear_error():
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.headers = {"Content-Type": "application/octet-stream"}
    resp.content = b"\xff\xfe\x00\x01binary"
    with patch("crate_builder.link_fetcher.requests.get", return_value=resp):
        with pytest.raises(LinkFetchError, match="Couldn't read that file as text"):
            fetch_tracklist_text("https://drive.google.com/file/d/fileid456/view")


def test_network_failure_raises_a_clear_error():
    with patch("crate_builder.link_fetcher.requests.get", side_effect=requests.RequestException("timeout")):
        with pytest.raises(LinkFetchError, match="Couldn't fetch that link"):
            fetch_tracklist_text("https://www.dropbox.com/s/abc123/setlist.txt?dl=0")
