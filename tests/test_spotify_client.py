from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlparse

import pytest

from crate_builder import spotify_client
from crate_builder.input_parser import InputTrack


@pytest.fixture(autouse=True)
def isolated_spotify(tmp_path, monkeypatch):
    monkeypatch.setattr(spotify_client, "_CACHE_PATH", str(tmp_path / "spotify_token_cache"))
    monkeypatch.setattr(spotify_client, "_SHARED_CLIENT_ID", "shared-client-id")
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    spotify_client._PENDING_LOGINS.clear()


def test_not_configured_without_any_client_id(monkeypatch):
    monkeypatch.setattr(spotify_client, "_SHARED_CLIENT_ID", "")
    with pytest.raises(spotify_client.SpotifyNotConfigured):
        spotify_client.get_oauth_manager()


def test_env_var_overrides_shared_client_id(monkeypatch):
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "my-own-app")
    manager = spotify_client.get_oauth_manager()
    assert manager.client_id == "my-own-app"


def test_get_login_url_uses_pkce_not_a_client_secret():
    url = spotify_client.get_login_url()
    params = parse_qs(urlparse(url).query)

    assert params["client_id"] == ["shared-client-id"]
    assert params["code_challenge_method"] == ["S256"]
    assert "code_challenge" in params
    assert "state" in params
    assert "client_secret" not in url
    assert len(spotify_client._PENDING_LOGINS) == 1


def test_handle_callback_rejects_unknown_state():
    with pytest.raises(spotify_client.SpotifyLoginExpired):
        spotify_client.handle_callback("some-code", "unknown-state")


def test_handle_callback_consumes_state_and_sends_matching_verifier():
    url = spotify_client.get_login_url()
    state = parse_qs(urlparse(url).query)["state"][0]
    expected_verifier = spotify_client._PENDING_LOGINS[state]

    captured = {}

    def fake_post(self, token_url, data=None, headers=None, **kwargs):
        captured.update(data)
        response = Mock()
        response.raise_for_status = Mock()
        response.json.return_value = {
            "access_token": "at",
            "refresh_token": "rt",
            "expires_in": 3600,
            "scope": spotify_client._SCOPE,
        }
        return response

    with patch("requests.Session.post", new=fake_post):
        spotify_client.handle_callback("auth-code", state)

    assert captured["code"] == "auth-code"
    assert captured["code_verifier"] == expected_verifier
    assert "client_secret" not in captured
    # State is single-use — a retry (or a second /callback hit) is rejected.
    with pytest.raises(spotify_client.SpotifyLoginExpired):
        spotify_client.handle_callback("auth-code", state)


def test_fetch_playlist_tracks_handles_new_item_key(monkeypatch):
    # Spotify's March 2026 migration to /playlists/{id}/items renamed each
    # entry's nested track object from "track" to "item".
    fake_sp = Mock()
    fake_sp.playlist_items.return_value = {
        "items": [{"item": {"name": "Song A", "artists": [{"name": "Artist A"}]}}],
        "next": None,
    }
    monkeypatch.setattr(spotify_client, "_get_client", lambda: fake_sp)

    tracks = spotify_client.fetch_playlist_tracks("playlist123")

    assert tracks == [InputTrack(artist="Artist A", title="Song A", raw="Artist A - Song A")]


def test_fetch_playlist_tracks_still_handles_old_track_key(monkeypatch):
    # Belt-and-suspenders: keep working if a response ever comes back in the
    # old shape too, since this couldn't be confirmed against the live API.
    fake_sp = Mock()
    fake_sp.playlist_items.return_value = {
        "items": [{"track": {"name": "Song B", "artists": [{"name": "Artist B"}]}}],
        "next": None,
    }
    monkeypatch.setattr(spotify_client, "_get_client", lambda: fake_sp)

    tracks = spotify_client.fetch_playlist_tracks("playlist123")

    assert tracks == [InputTrack(artist="Artist B", title="Song B", raw="Artist B - Song B")]


def test_fetch_playlist_tracks_paginates_and_skips_local_files(monkeypatch):
    # A local file (not on Spotify's servers) has no "item"/"track" object.
    page_one = {
        "items": [
            {"item": {"name": "Song A", "artists": [{"name": "Artist A"}]}},
            {"item": None},
        ],
        "next": "page2",
    }
    page_two = {
        "items": [{"item": {"name": "Song B", "artists": [{"name": "Artist B"}]}}],
        "next": None,
    }
    fake_sp = Mock()
    fake_sp.playlist_items.return_value = page_one
    fake_sp.next.return_value = page_two
    monkeypatch.setattr(spotify_client, "_get_client", lambda: fake_sp)

    tracks = spotify_client.fetch_playlist_tracks("playlist123")

    assert tracks == [
        InputTrack(artist="Artist A", title="Song A", raw="Artist A - Song A"),
        InputTrack(artist="Artist B", title="Song B", raw="Artist B - Song B"),
    ]
