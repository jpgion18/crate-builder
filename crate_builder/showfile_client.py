"""Sync a matched playlist to a Showfile (showfile.events) event.

Showfile is a separate, optional web app for DJs managing wedding gigs — see
https://github.com/jpgion18/showfile. If you use it, connect it on
crate-builder's own Settings page (site URL + API key, from Showfile's
"Playlist sync (crate-builder)" dashboard panel) and crate-builder can push
a matched playlist straight to an event's timeline suggestions.
"""

from __future__ import annotations

import os

import requests

from crate_builder import local_config


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
    api_url = (local_config.get("showfile_url") or os.environ.get("SHOWFILE_API_URL", "")).strip().rstrip("/")
    api_key = (local_config.get("showfile_api_key") or os.environ.get("SHOWFILE_API_KEY", "")).strip()
    if not api_url or not api_key:
        raise ShowfileNotConfigured(
            "Showfile isn't set up yet. Add it on the Settings page, or set "
            "SHOWFILE_API_URL / SHOWFILE_API_KEY in .env."
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
