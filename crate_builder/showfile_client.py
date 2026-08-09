"""Sync a matched playlist to a Showfile (showfile.events) event.

Showfile is a separate, optional web app for DJs managing wedding gigs — see
https://github.com/jpgion18/showfile. If you use it, its dashboard has a
"Playlist sync (crate-builder)" panel with your API key; set
SHOWFILE_API_URL / SHOWFILE_API_KEY and crate-builder can push a matched
playlist straight to an event's timeline suggestions.
"""

from __future__ import annotations

import os

import requests


class ShowfileNotConfigured(RuntimeError):
    pass


class ShowfileSyncError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def sync_playlist(event_code: str, tracks: list[dict]) -> dict:
    """POST a matched artist/title list to Showfile's /api/playlist.

    `tracks` is a list of {"artist": str, "title": str} dicts.
    """
    api_url = os.environ.get("SHOWFILE_API_URL", "").rstrip("/")
    api_key = os.environ.get("SHOWFILE_API_KEY", "")
    if not api_url or not api_key:
        raise ShowfileNotConfigured(
            "SHOWFILE_API_URL / SHOWFILE_API_KEY are not set. Copy .env.example "
            "to .env and fill them in from your Showfile dashboard's "
            '"Playlist sync (crate-builder)" panel.'
        )

    try:
        response = requests.post(
            f"{api_url}/api/playlist",
            json={"code": event_code, "tracks": tracks},
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
    except requests.RequestException as exc:
        raise ShowfileSyncError(f"Couldn't reach Showfile: {exc}") from None

    try:
        payload = response.json()
    except ValueError:
        payload = {}

    if not response.ok:
        message = payload.get("error", f"Showfile returned HTTP {response.status_code}")
        raise ShowfileSyncError(message, response.status_code)

    return payload
