"""Fetch playlist tracks from Spotify.

Uses the Authorization Code flow (a one-time browser login), not the
app-only Client Credentials flow. As of Spotify's late-2024 API policy
changes, an app-only token can only read playlists owned by the same
account that created the developer app — it gets a 403 Forbidden on any
other playlist, even public ones. Logging in as yourself removes that
restriction, matching what you'd see in the Spotify app itself.

Create free credentials at https://developer.spotify.com/dashboard.
"""

from __future__ import annotations

import os
import re

from crate_builder.input_parser import InputTrack

_PLAYLIST_URL_PATTERN = re.compile(r"open\.spotify\.com/playlist/([a-zA-Z0-9]+)")
_PLAYLIST_URI_PATTERN = re.compile(r"spotify:playlist:([a-zA-Z0-9]+)")

_SCOPE = "playlist-read-private playlist-read-collaborative"
_CACHE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".spotify_token_cache")


class SpotifyNotConfigured(RuntimeError):
    pass


class SpotifyNotConnected(RuntimeError):
    pass


def is_spotify_url(text: str) -> bool:
    text = text.strip()
    return bool(_PLAYLIST_URL_PATTERN.search(text) or _PLAYLIST_URI_PATTERN.search(text))


def extract_playlist_id(text: str) -> str | None:
    match = _PLAYLIST_URL_PATTERN.search(text) or _PLAYLIST_URI_PATTERN.search(text)
    return match.group(1) if match else None


def _redirect_uri() -> str:
    return os.environ.get("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:5001/callback")


def get_oauth_manager():
    from spotipy.oauth2 import SpotifyOAuth

    client_id = os.environ.get("SPOTIFY_CLIENT_ID")
    client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise SpotifyNotConfigured(
            "SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET are not set. "
            "Copy .env.example to .env and fill in credentials from "
            "https://developer.spotify.com/dashboard, or paste a plain-text/CSV "
            "track list instead of a Spotify URL."
        )
    return SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=_redirect_uri(),
        scope=_SCOPE,
        cache_path=_CACHE_PATH,
        open_browser=False,
    )


def is_connected() -> bool:
    try:
        oauth_manager = get_oauth_manager()
    except SpotifyNotConfigured:
        return False
    # A cached token (even expired) is enough — spotipy auto-refreshes it
    # using the stored refresh token on the next API call.
    return bool(oauth_manager.cache_handler.get_cached_token())


def get_login_url() -> str:
    return get_oauth_manager().get_authorize_url()


def handle_callback(auth_code: str) -> None:
    get_oauth_manager().get_access_token(auth_code, as_dict=False)


def _get_client():
    import spotipy

    oauth_manager = get_oauth_manager()
    token_info = oauth_manager.cache_handler.get_cached_token()
    if not token_info:
        raise SpotifyNotConnected(
            "Spotify isn't connected yet. Click 'Connect Spotify' and log in, "
            "then try again — or paste the track list as plain text/CSV instead."
        )
    return spotipy.Spotify(auth_manager=oauth_manager)


def fetch_playlist_tracks(playlist_url_or_id: str) -> list[InputTrack]:
    playlist_id = extract_playlist_id(playlist_url_or_id) or playlist_url_or_id.strip()
    sp = _get_client()

    tracks: list[InputTrack] = []
    results = sp.playlist_items(
        playlist_id,
        fields="items(track(name,artists(name))),next",
        additional_types=["track"],
    )
    while results:
        for item in results.get("items", []):
            track = item.get("track")
            if not track:
                continue
            title = track.get("name") or ""
            artists = ", ".join(a["name"] for a in track.get("artists", []) if a.get("name"))
            if title or artists:
                tracks.append(InputTrack(artist=artists, title=title, raw=f"{artists} - {title}"))
        results = sp.next(results) if results.get("next") else None

    return tracks
