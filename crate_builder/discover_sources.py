"""Persistent, named, gig-type-tagged bookmarks for where you go looking for
new music (a Spotify playlist, a DJ pool, a tracklist site, etc.) — lets
Discover's paste box pull from a reusable list instead of retyping a source
label every time. Categories organize these bookmarks only; the Discovery
Log itself stays one flat list, unaffected by any of this.
"""

from __future__ import annotations

import json
import os
import uuid

STORE_PATH = os.path.join(os.path.expanduser("~"), ".crate_builder", "discover_sources.json")

CATEGORIES = ["Wedding", "Brunch", "Happy Hour", "Club Open", "General"]
VALID_TYPES = {"Spotify", "Tracklist", "Blog", "Pool", "Social", "Other"}

# One-click "quick add" starting points per category — a convenience nudge
# carried over from the original concept this was ported from, not a fixed
# source of truth.
SUGGESTED = [
    {"name": "Spotify — Wedding Party", "type": "Spotify", "url": "", "category": "Wedding"},
    {"name": "Spotify — Today's Top Hits", "type": "Spotify", "url": "", "category": "General"},
    {"name": "Spotify — Feelin' Good", "type": "Spotify", "url": "", "category": "Brunch"},
    {"name": "Spotify — Cocktail Jazz", "type": "Spotify", "url": "", "category": "Happy Hour"},
    {"name": "Spotify — Dance Party", "type": "Spotify", "url": "", "category": "Club Open"},
    {
        "name": "1001tracklists — recent club sets",
        "type": "Tracklist",
        "url": "https://www.1001tracklists.com",
        "category": "Club Open",
    },
    {"name": "DJCity weekly pool picks", "type": "Pool", "url": "", "category": "General"},
    {"name": "TikTok sound trends", "type": "Social", "url": "", "category": "Wedding"},
]


def _load() -> list[dict]:
    try:
        with open(STORE_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return []


def _save(sources: list[dict]) -> None:
    os.makedirs(os.path.dirname(STORE_PATH), exist_ok=True)
    with open(STORE_PATH, "w") as f:
        json.dump(sources, f, indent=2)


def list_sources() -> list[dict]:
    return _load()


def add_source(name: str, url: str, source_type: str, category: str) -> dict:
    name = (name or "").strip()
    if not name:
        raise ValueError("Source name is required")
    if source_type not in VALID_TYPES:
        raise ValueError(f"Invalid type: {source_type!r}. Must be one of {sorted(VALID_TYPES)}.")
    if category not in CATEGORIES:
        raise ValueError(f"Invalid category: {category!r}. Must be one of {CATEGORIES}.")

    entry = {
        "id": uuid.uuid4().hex,
        "name": name,
        "url": (url or "").strip(),
        "type": source_type,
        "category": category,
    }
    sources = _load()
    sources.append(entry)
    _save(sources)
    return entry


def remove_source(source_id: str) -> bool:
    sources = _load()
    remaining = [s for s in sources if s["id"] != source_id]
    if len(remaining) == len(sources):
        return False
    _save(remaining)
    return True
