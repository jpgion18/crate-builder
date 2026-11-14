"""Desktop entry point: runs the Flask app in a background thread and opens
it in a native window via pywebview, so it launches like a normal app —
no terminal, no browser, no typing a localhost URL.

This is what PyInstaller packages into the CrateBuilder.app / CrateBuilder.exe
build (see desktop_app.spec and .github/workflows/build-desktop.yml). For
local development you can still run `python app.py` and use a browser.
"""

from __future__ import annotations

import os
import socket
import threading
import time
from pathlib import Path

import webview

from app import app, get_download
from crate_builder.myevents_poller import start_background_polling

HOST = "127.0.0.1"

# Tried in order and must match the redirect URIs registered on Spotify's
# side (spotify_client._redirect_uri() defaults to the first one) — Spotify
# requires an exact match, so binding to an arbitrary free port would break
# the OAuth callback. Only falls through to a random port (Spotify login
# unavailable that session, everything else unaffected) if all of these are
# already taken, e.g. another crate-builder instance already running.
_FIXED_PORTS = (5001, 5002, 5003)


def _try_fixed_port() -> int | None:
    for port in _FIXED_PORTS:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind((HOST, port))
            return port
        except OSError:
            continue
    return None


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


def _wait_until_up(port: int, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((HOST, port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("Crate Builder's local server didn't start in time")


class SaveApi:
    """Exposed to the page as window.pywebview.api (see static/download.js).

    Downloads are saved here instead of through the webview: pywebview on
    macOS re-fetches a download URL on its own after showing the Save
    dialog, and that kept saving a "405 Method Not Allowed" page in place of
    the Rekordbox XML. Here the bytes come straight from app._DOWNLOADS.
    """

    def __init__(self) -> None:
        # Underscore: pywebview exposes every public attribute to the page.
        self._window: webview.Window | None = None

    def save_download(self, token: str) -> dict:
        entry = get_download(token)
        if entry is None:
            return {"error": "This download has expired. Export it again."}
        data, filename = entry
        if self._window is None:
            return {"error": "The app window isn't ready yet. Try again."}

        downloads = Path.home() / "Downloads"
        chosen = self._window.create_file_dialog(
            webview.SAVE_DIALOG,
            directory=str(downloads) if downloads.is_dir() else "",
            save_filename=filename,
        )
        # A str on macOS, a tuple on Windows, None/empty if cancelled.
        if isinstance(chosen, (list, tuple)):
            chosen = chosen[0] if chosen else None
        if not chosen:
            return {"cancelled": True}
        try:
            Path(chosen).write_bytes(data)
        except OSError as exc:
            return {"error": f"Couldn't save {os.path.basename(chosen)}: {exc}"}
        return {"saved": str(chosen)}


def main() -> None:
    port = _try_fixed_port() or _free_port()
    server = threading.Thread(
        target=lambda: app.run(host=HOST, port=port, debug=False, use_reloader=False),
        daemon=True,
    )
    server.start()
    _wait_until_up(port)
    start_background_polling()

    # Off by default in pywebview — without it, a Content-Disposition:
    # attachment response (the Missing Tracks Log, Discovery Log export)
    # isn't recognized as a file to save at all; it's just silently
    # dropped, regardless of what triggered the request. This is what
    # turns it into a real native "Save File" dialog (defaulting to the
    # Downloads folder) on both macOS and Windows.
    webview.settings["ALLOW_DOWNLOADS"] = True

    api = SaveApi()
    api._window = webview.create_window(
        "Crate Builder", f"http://{HOST}:{port}", js_api=api, width=1100, height=850, min_size=(800, 600)
    )
    webview.start()


if __name__ == "__main__":
    main()
