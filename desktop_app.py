"""Desktop entry point: runs the Flask app in a background thread and opens
it in a native window via pywebview, so it launches like a normal app —
no terminal, no browser, no typing a localhost URL.

This is what PyInstaller packages into the CrateBuilder.app / CrateBuilder.exe
build (see desktop_app.spec and .github/workflows/build-desktop.yml). For
local development you can still run `python app.py` and use a browser.
"""

from __future__ import annotations

import socket
import threading
import time

import webview

from app import app
from crate_builder.myevents_poller import start_background_polling

HOST = "127.0.0.1"


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


def main() -> None:
    port = _free_port()
    server = threading.Thread(
        target=lambda: app.run(host=HOST, port=port, debug=False, use_reloader=False),
        daemon=True,
    )
    server.start()
    _wait_until_up(port)
    start_background_polling()

    webview.create_window("Crate Builder", f"http://{HOST}:{port}", width=1100, height=850, min_size=(800, 600))
    webview.start()


if __name__ == "__main__":
    main()
