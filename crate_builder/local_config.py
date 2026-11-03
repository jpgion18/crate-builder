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

_KEYS = (
    "showfile_url",
    "showfile_api_key",
    "showfile_business_name",
    "community_url",
    "community_access_code",
)


# Remembered choices that aren't Settings-page settings (so get_settings()
# and the Settings API don't change), with their allowed values.
_PREFERENCES = {
    "build_target": ("serato", "rekordbox", "both"),  # what Build Crate writes
}


def _read_raw() -> dict:
    try:
        with open(_CONFIG_PATH) as f:
            data = json.load(f)
    except (FileNotFoundError, ValueError):
        data = {}
    return data if isinstance(data, dict) else {}


def _read() -> dict:
    data = _read_raw()
    return {key: data.get(key, "") for key in _KEYS}


def _write(data: dict) -> None:
    os.makedirs(os.path.dirname(_CONFIG_PATH), exist_ok=True)
    with open(_CONFIG_PATH, "w") as f:
        json.dump(data, f, indent=2)


def get_settings() -> dict:
    return _read()


def update_settings(**kwargs: str) -> dict:
    for key in kwargs:
        if key not in _KEYS:
            raise ValueError(f"Unknown setting: {key}")
    raw = _read_raw()  # keeps preferences saved alongside
    for key, value in kwargs.items():
        if value is not None:
            raw[key] = value.strip()
    _write(raw)
    return {key: raw.get(key, "") for key in _KEYS}


def get_preference(key: str, default: str) -> str:
    """A remembered choice, or `default` if unset or no longer a valid value."""
    if key not in _PREFERENCES:
        raise ValueError(f"Unknown preference: {key}")
    value = _read_raw().get(key)
    return value if value in _PREFERENCES[key] else default


def set_preference(key: str, value: str) -> None:
    if key not in _PREFERENCES:
        raise ValueError(f"Unknown preference: {key}")
    if value not in _PREFERENCES[key]:
        raise ValueError(f"Invalid value for {key}: {value}")
    raw = _read_raw()
    raw[key] = value
    _write(raw)


def get(key: str) -> str:
    if key not in _KEYS:
        raise ValueError(f"Unknown setting: {key}")
    return _read()[key]
