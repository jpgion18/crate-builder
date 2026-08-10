"""Local storage for user-entered settings: your Showfile connection (site
URL, API key) and Community access code. A single small file in your home
directory, filled in once via the Settings page — not `.env`, not something
you're expected to hand-edit.

Values here take priority over the matching environment variables
(SHOWFILE_API_URL, SHOWFILE_API_KEY, COMMUNITY_API_URL) when both are
present, so an existing `.env`-based setup keeps working untouched until
you save something in Settings.
"""

from __future__ import annotations

import json
import os

_CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".crate_builder", "config.json")

_KEYS = ("showfile_url", "showfile_api_key", "community_url", "community_access_code")


def _read() -> dict:
    try:
        with open(_CONFIG_PATH) as f:
            data = json.load(f)
    except (FileNotFoundError, ValueError):
        data = {}
    return {key: data.get(key, "") for key in _KEYS}


def _write(data: dict) -> None:
    os.makedirs(os.path.dirname(_CONFIG_PATH), exist_ok=True)
    with open(_CONFIG_PATH, "w") as f:
        json.dump(data, f, indent=2)


def get_settings() -> dict:
    return _read()


def update_settings(**kwargs: str) -> dict:
    data = _read()
    for key, value in kwargs.items():
        if key not in _KEYS:
            raise ValueError(f"Unknown setting: {key}")
        if value is not None:
            data[key] = value.strip()
    _write(data)
    return data


def get(key: str) -> str:
    if key not in _KEYS:
        raise ValueError(f"Unknown setting: {key}")
    return _read()[key]
