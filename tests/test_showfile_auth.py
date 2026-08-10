import base64
import hashlib
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlparse

import pytest

from crate_builder import local_config, showfile_auth


def test_start_login_builds_valid_pkce_challenge():
    authorize_url, state, verifier = showfile_auth.start_login("http://127.0.0.1:5001/showfile/callback")

    parsed = urlparse(authorize_url)
    assert parsed.path == "/crate-builder/authorize"
    params = parse_qs(parsed.query)

    assert params["redirect_uri"] == ["http://127.0.0.1:5001/showfile/callback"]
    assert params["state"] == [state]
    assert params["code_challenge_method"] == ["S256"]

    expected_challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    assert params["code_challenge"] == [expected_challenge]
    assert 43 <= len(verifier) <= 128


def test_start_login_uses_showfile_url_from_settings():
    local_config.update_settings(showfile_url="https://custom.showfile.example")
    authorize_url, _, _ = showfile_auth.start_login("http://127.0.0.1:5001/showfile/callback")
    assert authorize_url.startswith("https://custom.showfile.example/crate-builder/authorize?")


def test_start_login_defaults_to_production_showfile_url():
    authorize_url, _, _ = showfile_auth.start_login("http://127.0.0.1:5001/showfile/callback")
    assert authorize_url.startswith("https://www.showfile.events/crate-builder/authorize?")


def test_exchange_code_posts_expected_request():
    local_config.update_settings(showfile_url="https://www.showfile.events")

    mock_response = Mock(ok=True)
    mock_response.json.return_value = {
        "api_key": "api-key-123",
        "crate_builder_code": "cbc-456",
        "business_name": "DJ Test",
    }

    with patch("crate_builder.showfile_auth.requests.post", return_value=mock_response) as mock_post:
        result = showfile_auth.exchange_code("auth-code", "verifier-xyz", "http://127.0.0.1:5001/showfile/callback")

    assert result == {"api_key": "api-key-123", "crate_builder_code": "cbc-456", "business_name": "DJ Test"}
    mock_post.assert_called_once_with(
        "https://www.showfile.events/api/crate-builder/token",
        json={
            "code": "auth-code",
            "code_verifier": "verifier-xyz",
            "redirect_uri": "http://127.0.0.1:5001/showfile/callback",
        },
        timeout=10,
    )


def test_exchange_code_raises_on_error_response():
    mock_response = Mock(ok=False, status_code=400)
    mock_response.json.return_value = {"error": "Invalid or expired code"}

    with patch("crate_builder.showfile_auth.requests.post", return_value=mock_response):
        with pytest.raises(showfile_auth.ShowfileAuthError) as exc_info:
            showfile_auth.exchange_code("bad-code", "verifier", "http://127.0.0.1:5001/showfile/callback")

    assert "Invalid or expired code" in str(exc_info.value)
