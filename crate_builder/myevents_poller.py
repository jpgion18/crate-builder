"""Poll Showfile's GET /api/playlist/pending — the automated half of
Playlist Sync: instead of a DJ manually pasting/exporting a track list per
event, this pulls current songs across every Booked+ event and updates
the local cache the MyEvents tab reads from. The push side (reviewing
matches, POST /api/playlist) is unchanged and stays manual — see
showfile_client.py.
"""

from __future__ import annotations

import os
import threading
import time

import requests

from crate_builder import local_config, pending_store

POLL_INTERVAL_SECONDS = 5 * 60


class ShowfilePendingError(RuntimeError):
    pass


def _showfile_credentials() -> tuple[str, str]:
    api_url = (local_config.get("showfile_url") or os.environ.get("SHOWFILE_API_URL", "")).strip().rstrip("/")
    api_key = (local_config.get("showfile_api_key") or os.environ.get("SHOWFILE_API_KEY", "")).strip()
    return api_url, api_key


def fetch_pending() -> list[dict]:
    """One live call to GET /api/playlist/pending. Raises ShowfilePendingError
    on any failure — callers decide whether that's fatal (a manual refresh
    button) or just something to retry next cycle (the background loop)."""
    api_url, api_key = _showfile_credentials()
    if not api_url or not api_key:
        raise ShowfilePendingError("Showfile isn't connected.")

    try:
        response = requests.get(
            f"{api_url}/api/playlist/pending",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
    except requests.RequestException as exc:
        raise ShowfilePendingError(f"Couldn't reach Showfile: {exc}") from None

    if response.status_code == 401:
        # Same "stored credential rejected" handling as showfile_client.py.
        local_config.update_settings(showfile_api_key="", showfile_business_name="")
        raise ShowfilePendingError("Showfile rejected the stored API key.")
    if not response.ok:
        raise ShowfilePendingError(f"Showfile returned HTTP {response.status_code}")

    try:
        payload = response.json()
    except ValueError:
        raise ShowfilePendingError("Showfile returned an invalid response.") from None

    return payload.get("events", [])


def poll_once() -> list[dict]:
    """Fetch live and update the local cache. Raises ShowfilePendingError on failure."""
    return pending_store.update_from_poll(fetch_pending())


def start_background_polling() -> None:
    """Fire-and-forget: a daemon thread that polls every POLL_INTERVAL_SECONDS
    while Showfile is connected, and just idles (not errors) otherwise —
    a DJ might connect Showfile later in the same session. Call this once,
    from an actual entry point (app.py's __main__, desktop_app.py) — never
    at module import time, or every test run would spawn a thread."""

    def _loop():
        while True:
            _, api_key = _showfile_credentials()
            if api_key:
                try:
                    poll_once()
                except ShowfilePendingError:
                    pass  # best-effort; try again next cycle
            time.sleep(POLL_INTERVAL_SECONDS)

    threading.Thread(target=_loop, daemon=True).start()
