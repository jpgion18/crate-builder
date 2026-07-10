"""Fetch playlist tracks from Spotify using the app-only (Client Credentials) flow.

Only needs a Client ID/Secret (no user login) since it only reads public
playlist data. Create free credentials at
https://developer.spotify.com/dashboard.
"""

from __future__ import annotations

import os
import re

from crate_builder.input_parser import InputTrack

_PLAYLIST_URL_PATTERN = re.compile(r"open\.spotify\.com/playlist/([a-zA-Z0-9]+)")
_PLAYLIST_URI_PATTERN = re.compile(r"spotify:playlist:([a-zA-Z0-9]+)")


class SpotifyNotConfigured(RuntimeError):
    pass


def is_spotify_url(text: str) -> bool:
    text = text.strip()
    return bool(_PLAYLIST_URL_PATTERN.search(text) or _PLAYLIST_URI_PATTERN.search(text))


def extract_playlist_id(text: str) -> str | None:
    match = _PLAYLIST_URL_PATTERN.search(text) or _PLAYLIST_URI_PATTERN.search(text)
    return match.group(1) if match else None


def _get_client():
    import spotipy
    from spotipy.oauth2 import SpotifyClientCredentials

    client_id = os.environ.get("SPOTIFY_CLIENT_ID")
    client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise SpotifyNotConfigured(
            "SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET are not set. "
            "Copy .env.example to .env and fill in credentials from "
            "https://developer.spotify.com/dashboard, or paste a plain-text/CSV "
            "track list instead of a Spotify URL."
        )
    auth_manager = SpotifyClientCredentials(client_id=client_id, client_secret=client_secret)
    return spotipy.Spotify(auth_manager=auth_manager)


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
