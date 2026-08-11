"""Fetch playlist tracks from Spotify.

Uses the Authorization Code flow with PKCE (RFC 7636) rather than a
classic client-secret flow, because this app ships as a distributed
desktop binary — a `client_secret` embedded in it wouldn't actually be
secret (anyone can extract it from the binary). PKCE is the flow Spotify
itself recommends for exactly this case: only a `client_id` is needed,
which is safe to publish, and the per-request code_verifier/code_challenge
pair stands in for the secret. Every install shares one crate-builder
Spotify app (_SHARED_CLIENT_ID below) so nobody has to create their own —
each person still does their own one-time login, so this doesn't grant
crate-builder any access beyond what that person's account allows.

Login itself is still a real (one-time) browser login rather than app-only
auth, because Spotify's API no longer allows app-only tokens to read
playlists they don't own — even public ones. Logging in lets it read any
playlist the logged-in user can see.

Run your own Spotify app instead by setting SPOTIFY_CLIENT_ID in .env —
that overrides the shared one.
"""

from __future__ import annotations

import os
import re
import secrets

from crate_builder.input_parser import InputTrack

_PLAYLIST_URL_PATTERN = re.compile(r"open\.spotify\.com/playlist/([a-zA-Z0-9]+)")
_PLAYLIST_URI_PATTERN = re.compile(r"spotify:playlist:([a-zA-Z0-9]+)")

_SCOPE = "playlist-read-private playlist-read-collaborative"
_CACHE_PATH = os.path.join(os.path.expanduser("~"), ".crate_builder", "spotify_token_cache")

# crate-builder's own Spotify app (PKCE, no secret) — shared by every
# download so "Connect Spotify" works with zero setup. Falls back to
# SPOTIFY_CLIENT_ID from .env for anyone running their own app instead.
_SHARED_CLIENT_ID = "e130117bfea2435a8a836b26c685ec18"

# state -> code_verifier, for logins currently in progress. PKCE's
# code_verifier is generated when the authorize URL is built (in /login)
# but only needed again once Spotify redirects back with a code (in
# /callback) — a separate request, so it can't just live on a local
# variable. Keyed by state both to survive that gap and as CSRF protection.
_PENDING_LOGINS: dict[str, str] = {}


class SpotifyNotConfigured(RuntimeError):
    pass


class SpotifyNotConnected(RuntimeError):
    pass


class SpotifyLoginExpired(RuntimeError):
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
    from spotipy.oauth2 import CacheFileHandler, SpotifyPKCE

    client_id = os.environ.get("SPOTIFY_CLIENT_ID", "").strip() or _SHARED_CLIENT_ID
    if not client_id:
        raise SpotifyNotConfigured(
            "Spotify isn't configured — this build is missing its shared "
            "client ID. Set SPOTIFY_CLIENT_ID in .env to use your own "
            "Spotify Developer app instead, or paste a plain-text/CSV "
            "track list instead of a Spotify URL."
        )
    os.makedirs(os.path.dirname(_CACHE_PATH), exist_ok=True)
    return SpotifyPKCE(
        client_id=client_id,
        redirect_uri=_redirect_uri(),
        scope=_SCOPE,
        cache_handler=CacheFileHandler(cache_path=_CACHE_PATH),
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
    oauth_manager = get_oauth_manager()
    oauth_manager.get_pkce_handshake_parameters()
    state = secrets.token_urlsafe(16)
    _PENDING_LOGINS[state] = oauth_manager.code_verifier
    return oauth_manager.get_authorize_url(state=state)


def handle_callback(auth_code: str, state: str) -> None:
    code_verifier = _PENDING_LOGINS.pop(state, None)
    if not code_verifier:
        raise SpotifyLoginExpired(
            "Spotify login expired or was already used — click 'Connect Spotify' and try again."
        )
    oauth_manager = get_oauth_manager()
    oauth_manager.code_verifier = code_verifier
    # get_access_token() regenerates the verifier from scratch (discarding
    # the one above) unless code_challenge is also set — it isn't actually
    # sent in the token exchange, but its presence is what tells spotipy
    # the handshake already happened.
    oauth_manager.code_challenge = oauth_manager._get_code_challenge()
    oauth_manager.get_access_token(auth_code, check_cache=False)


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
