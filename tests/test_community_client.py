from unittest.mock import Mock, patch

import pytest

from crate_builder import community_client


@pytest.fixture(autouse=True)
def community_code_path(tmp_path, monkeypatch):
    """Redirect the access-code file to a temp path so tests don't touch ~/.crate_builder/."""
    monkeypatch.setattr(community_client, "_CODE_PATH", str(tmp_path / "community_access_code"))


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
