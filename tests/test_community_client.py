from unittest.mock import Mock, patch

import pytest

from crate_builder import community_client, local_config


def test_get_access_code_returns_empty_when_unset():
    assert community_client.get_access_code() == ""


def test_set_and_get_access_code_round_trip():
    community_client.set_access_code("  my-code  ")
    assert community_client.get_access_code() == "my-code"


def test_publish_crate_raises_when_not_configured(monkeypatch):
    monkeypatch.delenv("COMMUNITY_API_URL", raising=False)
    community_client.set_access_code("my-code")

    with pytest.raises(community_client.CommunityNotConfigured):
        community_client.publish_crate("My Crate", [{"artist": "A", "title": "B"}])


def test_publish_crate_raises_when_no_access_code(monkeypatch):
    monkeypatch.setenv("COMMUNITY_API_URL", "https://community.example.com")

    with pytest.raises(community_client.CommunityAccessCodeMissing):
        community_client.publish_crate("My Crate", [{"artist": "A", "title": "B"}])


def test_publish_crate_posts_expected_request(monkeypatch):
    monkeypatch.setenv("COMMUNITY_API_URL", "https://community.example.com")
    community_client.set_access_code("my-code")

    mock_response = Mock(ok=True)
    mock_response.json.return_value = {"ok": True, "id": "abc-123"}

    with patch("crate_builder.community_client.requests.request", return_value=mock_response) as mock_request:
        tracks = [{"artist": "Artist A", "title": "Song One"}]
        result = community_client.publish_crate("My Crate", tracks, tag="techno", display_name="DJ Test")

    assert result == {"ok": True, "id": "abc-123"}
    mock_request.assert_called_once_with(
        "POST",
        "https://community.example.com/api/crates",
        timeout=10,
        headers={"Authorization": "Bearer my-code"},
        json={"crate_name": "My Crate", "tracks": tracks, "tag": "techno", "display_name": "DJ Test"},
    )


def test_publish_crate_raises_on_error_response(monkeypatch):
    monkeypatch.setenv("COMMUNITY_API_URL", "https://community.example.com")
    community_client.set_access_code("my-code")

    mock_response = Mock(ok=False, status_code=429)
    mock_response.json.return_value = {"error": "Too many requests"}

    with patch("crate_builder.community_client.requests.request", return_value=mock_response):
        with pytest.raises(community_client.CommunityRequestError) as exc_info:
            community_client.publish_crate("My Crate", [{"artist": "A", "title": "B"}])

    assert "Too many requests" in str(exc_info.value)
    assert exc_info.value.status_code == 429


def test_list_crates_builds_query_params(monkeypatch):
    monkeypatch.setenv("COMMUNITY_API_URL", "https://community.example.com")
    community_client.set_access_code("my-code")

    mock_response = Mock(ok=True)
    mock_response.json.return_value = {"crates": [], "total": 0}

    with patch("crate_builder.community_client.requests.request", return_value=mock_response) as mock_request:
        result = community_client.list_crates(query="techno", limit=10, offset=20)

    assert result == {"crates": [], "total": 0}
    mock_request.assert_called_once_with(
        "GET",
        "https://community.example.com/api/crates",
        timeout=10,
        headers={"Authorization": "Bearer my-code"},
        params={"limit": 10, "offset": 20, "q": "techno"},
    )


def test_list_crates_clears_stored_code_on_401(monkeypatch):
    monkeypatch.setenv("COMMUNITY_API_URL", "https://community.example.com")
    community_client.set_access_code("stale-code")

    mock_response = Mock(ok=False, status_code=401)
    mock_response.json.return_value = {"error": "Invalid access code"}

    with patch("crate_builder.community_client.requests.request", return_value=mock_response):
        with pytest.raises(community_client.CommunityRequestError):
            community_client.list_crates()

    assert community_client.get_access_code() == ""


def test_list_crates_keeps_stored_code_on_403():
    community_client.set_access_code("valid-but-unentitled-code")
    local_config.update_settings(community_url="https://community.example.com")

    mock_response = Mock(ok=False, status_code=403)
    mock_response.json.return_value = {"error": "Your Showfile subscription isn't active"}

    with patch("crate_builder.community_client.requests.request", return_value=mock_response):
        with pytest.raises(community_client.CommunityRequestError):
            community_client.list_crates()

    assert community_client.get_access_code() == "valid-but-unentitled-code"


def test_url_and_code_prefer_local_config_over_env(monkeypatch):
    monkeypatch.setenv("COMMUNITY_API_URL", "https://env.example.com")
    local_config.update_settings(community_url="https://settings.example.com", community_access_code="settings-code")

    mock_response = Mock(ok=True)
    mock_response.json.return_value = {"crates": [], "total": 0}

    with patch("crate_builder.community_client.requests.request", return_value=mock_response) as mock_request:
        community_client.list_crates()

    mock_request.assert_called_once_with(
        "GET",
        "https://settings.example.com/api/crates",
        timeout=10,
        headers={"Authorization": "Bearer settings-code"},
        params={"limit": 20, "offset": 0},
    )
