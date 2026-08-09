from unittest.mock import Mock, patch

import pytest

from crate_builder import showfile_client


def test_sync_playlist_raises_when_not_configured(monkeypatch):
    monkeypatch.delenv("SHOWFILE_API_URL", raising=False)
    monkeypatch.delenv("SHOWFILE_API_KEY", raising=False)

    with pytest.raises(showfile_client.ShowfileNotConfigured):
        showfile_client.sync_playlist("KATIE-DREW-1004", [{"artist": "A", "title": "B"}])


def test_sync_playlist_posts_expected_request(monkeypatch):
    monkeypatch.setenv("SHOWFILE_API_URL", "https://showfile.events")
    monkeypatch.setenv("SHOWFILE_API_KEY", "secret-key")

    mock_response = Mock(ok=True)
    mock_response.json.return_value = {"ok": True, "count": 2}

    with patch("crate_builder.showfile_client.requests.post", return_value=mock_response) as mock_post:
        tracks = [{"artist": "Artist A", "title": "Song One"}, {"artist": "Artist B", "title": "Song Two"}]
        result = showfile_client.sync_playlist("KATIE-DREW-1004", tracks)

    assert result == {"ok": True, "count": 2}
    mock_post.assert_called_once_with(
        "https://showfile.events/api/playlist",
        json={"code": "KATIE-DREW-1004", "tracks": tracks},
        headers={"Authorization": "Bearer secret-key"},
        timeout=10,
    )


def test_sync_playlist_raises_on_error_response(monkeypatch):
    monkeypatch.setenv("SHOWFILE_API_URL", "https://showfile.events")
    monkeypatch.setenv("SHOWFILE_API_KEY", "bad-key")

    mock_response = Mock(ok=False, status_code=401)
    mock_response.json.return_value = {"error": "Invalid API key"}

    with patch("crate_builder.showfile_client.requests.post", return_value=mock_response):
        with pytest.raises(showfile_client.ShowfileSyncError) as exc_info:
            showfile_client.sync_playlist("KATIE-DREW-1004", [{"artist": "A", "title": "B"}])

    assert "Invalid API key" in str(exc_info.value)
    assert exc_info.value.status_code == 401
