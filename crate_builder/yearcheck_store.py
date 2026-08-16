"""Local cache of MusicBrainz year-check results, keyed by normalized
artist+title, so results survive across app restarts and re-running the
checker automatically skips anything already checked. That's what makes a
multi-hour check of a large library resumable without the manual
JSON-export/reload step the original concept prototype needed.
"""

from __future__ import annotations

import json
import os

STORE_PATH = os.path.join(os.path.expanduser("~"), ".crate_builder", "year_check_results.json")


def _key(artist: str, title: str) -> str:
    return f"{(artist or '').strip().lower()}||{(title or '').strip().lower()}"


def _load() -> dict:
    try:
        with open(STORE_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}


def _save(data: dict) -> None:
    os.makedirs(os.path.dirname(STORE_PATH), exist_ok=True)
    with open(STORE_PATH, "w") as f:
        json.dump(data, f, indent=2)


def get_cached_results() -> list[dict]:
    return list(_load().values())


def is_checked(artist: str, title: str) -> bool:
    return _key(artist, title) in _load()


def save_result(artist: str, title: str, result: dict) -> None:
    data = _load()
    data[_key(artist, title)] = result
    _save(data)


def clear_cache() -> None:
    _save({})
