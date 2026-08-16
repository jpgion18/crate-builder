"""Checks GitHub's Releases API for a version newer than the one currently
running, so Settings can show a lightweight "update available" banner.

Read-only and best-effort: any failure (offline, GitHub down, rate
limited) just means no banner shows — never an error the user has to deal
with. Never auto-downloads or auto-installs anything — these builds are
unsigned, so replacing a running app safely isn't something to attempt
without proper code signing in place first. This only ever surfaces a link
to the GitHub release page for the user to grab manually, same as the
existing download flow.
"""

from __future__ import annotations

import json
import os
import time

import requests

RELEASES_LATEST_URL = "https://api.github.com/repos/jpgion18/crate-builder/releases/latest"
CHECK_INTERVAL_SECONDS = 24 * 60 * 60  # once a day is plenty for a desktop app
CACHE_PATH = os.path.join(os.path.expanduser("~"), ".crate_builder", "update_check.json")

_NO_UPDATE = {"update_available": False, "latest_version": None, "release_url": None}


def _load_cache() -> dict:
    try:
        with open(CACHE_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}


def _save_cache(data: dict) -> None:
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w") as f:
        json.dump(data, f, indent=2)


def _fetch_latest_release() -> dict | None:
    # Broad except is deliberate: this must never raise, whether that's a
    # connection failure, a timeout, or GitHub returning something that
    # doesn't parse as expected — any of those just means "no update info
    # this time," not a crash.
    try:
        response = requests.get(
            RELEASES_LATEST_URL, timeout=10, headers={"Accept": "application/vnd.github+json"}
        )
        if not response.ok:
            return None
        data = response.json()
        tag_name = data.get("tag_name")
        html_url = data.get("html_url")
        if not tag_name or not html_url:
            return None
        return {"tag_name": tag_name, "html_url": html_url}
    except Exception:
        return None


def check_for_update(current_version: str, force: bool = False) -> dict:
    """Returns {"update_available", "latest_version", "release_url"}.
    Never raises — any failure just reports no update available."""
    # A source checkout / manual build has no real version to compare —
    # comparing "dev" against a real tag would always (wrongly) look like
    # an update is available.
    if not current_version or current_version == "dev":
        return dict(_NO_UPDATE)

    cache = _load_cache()
    now = time.time()
    is_stale = force or not cache.get("checked_at") or now - cache["checked_at"] >= CHECK_INTERVAL_SECONDS

    if is_stale:
        release = _fetch_latest_release()
        if release:
            cache = {"checked_at": now, "latest_version": release["tag_name"], "release_url": release["html_url"]}
            _save_cache(cache)
        elif not cache:
            # No fresh data and nothing cached from before — nothing to report.
            return dict(_NO_UPDATE)
        # else: fetch failed but a stale cache exists — use it rather than
        # flapping the banner on/off over a transient network blip.

    latest = cache.get("latest_version")
    if not latest or latest == current_version:
        return dict(_NO_UPDATE)
    return {"update_available": True, "latest_version": latest, "release_url": cache.get("release_url")}
