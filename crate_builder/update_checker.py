"""Checks GitHub's Releases API for a version newer than the one currently
running, so Settings can show a lightweight "update available" banner.
Compares versions numerically (_is_newer), not just for inequality — the
cached "latest" can end up older than what's actually running (e.g. you
checked while on an older build, then jumped straight to installing a
newer one before the cache expired), and a plain != check would wrongly
call that stale cache an "update."

Read-only and best-effort: any failure (offline, GitHub down, rate
limited) just means no banner shows — never an error the user has to deal
with. Never auto-installs anything — these builds are unsigned, so
replacing a running app safely isn't something to attempt without proper
code signing in place first. This surfaces a direct link to *download* the
right zip for the current OS (not just the release page), reusing GitHub's
stable /releases/latest/download/<asset> pattern — same mechanism as the
"Download for Mac/Windows" buttons on the community site — but stops
short of installing it.
"""

from __future__ import annotations

import json
import os
import sys
import time

import requests

RELEASES_LATEST_URL = "https://api.github.com/repos/jpgion18/crate-builder/releases/latest"
CHECK_INTERVAL_SECONDS = 24 * 60 * 60  # once a day is plenty for a desktop app
CACHE_PATH = os.path.join(os.path.expanduser("~"), ".crate_builder", "update_check.json")

# sys.platform of the machine this is actually running on -> the matching
# release asset, same filenames build-desktop.yml has always published.
_ASSET_NAMES = {
    "darwin": "CrateBuilder-macos.zip",
    "win32": "CrateBuilder-windows.zip",
}

_NO_UPDATE = {"update_available": False, "latest_version": None, "release_url": None, "download_url": None}


def _asset_download_url() -> str | None:
    asset_name = _ASSET_NAMES.get(sys.platform)
    if not asset_name:
        return None
    return f"https://github.com/jpgion18/crate-builder/releases/latest/download/{asset_name}"


def _parse_version(version: str) -> tuple[int, ...] | None:
    """"v0.9.2" -> (0, 9, 2). None if it doesn't parse as plain dotted
    integers, so a weird/non-semver tag never crashes this — it just
    can't be compared numerically."""
    try:
        return tuple(int(p) for p in version.lstrip("v").split("."))
    except ValueError:
        return None


def _is_newer(candidate: str, current: str) -> bool:
    """True only if candidate is an actually newer version than current —
    not just a different string. Matters because the cached "latest" can
    be older than what's actually running: check while still on v0.9.0,
    cache says v0.9.1, then jump straight to installing v0.9.2 — a plain
    inequality check would wrongly call that stale v0.9.1 an "update."
    Falls back to simple inequality if either side doesn't parse as plain
    semver, so an unusual tag format still degrades safely."""
    candidate_parsed = _parse_version(candidate)
    current_parsed = _parse_version(current)
    if candidate_parsed is None or current_parsed is None:
        return candidate != current
    return candidate_parsed > current_parsed


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
    """Returns {"update_available", "latest_version", "release_url",
    "download_url"}. download_url is the direct link to the zip matching
    the OS this is actually running on, or None on a platform without a
    published build (e.g. Linux). Never raises — any failure just reports
    no update available."""
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
    if not latest or not _is_newer(latest, current_version):
        return dict(_NO_UPDATE)
    return {
        "update_available": True,
        "latest_version": latest,
        "release_url": cache.get("release_url"),
        "download_url": _asset_download_url(),
    }
