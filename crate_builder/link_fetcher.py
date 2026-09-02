"""Fetch a tracklist's raw text from a Dropbox or Google Drive/Docs/Sheets
share link, so pasting a link works the same as pasting the list itself.

Only handles links shared as "anyone with the link" — no OAuth, no login,
same tradeoff as Spotify playlist URLs needing a public/accessible
playlist. A private file just fails to fetch, the same way opening it in
an incognito browser tab would.
"""

from __future__ import annotations

import re

import requests

_REQUEST_TIMEOUT = 15

_DOCS_PATTERN = re.compile(r"docs\.google\.com/document/d/([\w-]+)")
_SHEETS_PATTERN = re.compile(r"docs\.google\.com/spreadsheets/d/([\w-]+)")
_DRIVE_FILE_PATTERN = re.compile(r"drive\.google\.com/file/d/([\w-]+)")
_DRIVE_OPEN_PATTERN = re.compile(r"drive\.google\.com/open\?id=([\w-]+)")


class LinkFetchError(RuntimeError):
    pass


def is_shared_link(text: str) -> bool:
    text = text.lower()
    return "dropbox.com" in text or "drive.google.com" in text or "docs.google.com" in text


def fetch_tracklist_text(url: str) -> str:
    """Returns the raw text content behind a Dropbox or Google share link."""
    direct_url = _to_direct_url(url.strip())
    try:
        response = requests.get(direct_url, timeout=_REQUEST_TIMEOUT, allow_redirects=True)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise LinkFetchError(f"Couldn't fetch that link: {exc}") from exc

    # A share link that isn't actually public (or needs a Google/Dropbox
    # login) resolves to a sign-in/HTML page rather than the file itself —
    # catch that before trying to decode it as a tracklist.
    if "text/html" in response.headers.get("Content-Type", ""):
        raise LinkFetchError(
            "That link didn't return the file itself — make sure it's shared "
            "as \"Anyone with the link\" (not just specific people), then try again."
        )

    try:
        return response.content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise LinkFetchError(
            "Couldn't read that file as text — only .txt/.csv files, Google Docs, "
            "and Google Sheets are supported (not .docx, .pdf, or other formats)."
        ) from exc


def _to_direct_url(url: str) -> str:
    docs_match = _DOCS_PATTERN.search(url)
    if docs_match:
        return f"https://docs.google.com/document/d/{docs_match.group(1)}/export?format=txt"

    sheets_match = _SHEETS_PATTERN.search(url)
    if sheets_match:
        return f"https://docs.google.com/spreadsheets/d/{sheets_match.group(1)}/export?format=csv"

    drive_match = _DRIVE_FILE_PATTERN.search(url) or _DRIVE_OPEN_PATTERN.search(url)
    if drive_match:
        return f"https://drive.google.com/uc?export=download&id={drive_match.group(1)}"

    if "dropbox.com" in url.lower():
        # dl=1 forces Dropbox to serve the raw file instead of its HTML
        # preview page — same file, just skipping the web UI around it.
        if re.search(r"[?&]dl=0\b", url):
            return re.sub(r"([?&])dl=0\b", r"\1dl=1", url)
        if re.search(r"[?&]dl=1\b", url):
            return url
        return url + ("&" if "?" in url else "?") + "dl=1"

    return url
