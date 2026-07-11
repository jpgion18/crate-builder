"""Persistent local log of tracks discovered from other DJs' sets/charts/playlists
that aren't in your library yet — a running "to check out" list, separate from
crate building. Stored as a flat JSON file so there's no database to set up.
"""

from __future__ import annotations

import csv
import io
import json
import os
import uuid
from datetime import datetime, timezone

from crate_builder.matcher import normalize

STORE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "discovery_log.json")

VALID_STATUSES = {"new", "acquired", "dismissed"}


def _load(store_path: str = STORE_PATH) -> list[dict]:
    if not os.path.exists(store_path):
        return []
    with open(store_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(entries: list[dict], store_path: str = STORE_PATH) -> None:
    with open(store_path, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2)


def _dedup_key(artist: str, title: str) -> str:
    return normalize(f"{artist} {title}")


def list_entries(store_path: str = STORE_PATH) -> list[dict]:
    return sorted(_load(store_path), key=lambda e: e["date_added"], reverse=True)


def add_entries(candidates: list[dict], source: str, store_path: str = STORE_PATH) -> dict:
    """candidates: list of {"artist": .., "title": .., "raw": ..}.

    Skips anything that normalizes to the same artist+title as an entry
    already in the log, so pasting overlapping tracklists over time doesn't
    pile up duplicates.
    """
    existing = _load(store_path)
    existing_keys = {_dedup_key(e["artist"], e["title"]) for e in existing}

    added = []
    skipped = 0
    now = datetime.now(timezone.utc).isoformat()

    for c in candidates:
        artist = c.get("artist", "")
        title = c.get("title", "")
        key = _dedup_key(artist, title)
        if not key or key in existing_keys:
            skipped += 1
            continue
        entry = {
            "id": uuid.uuid4().hex,
            "artist": artist,
            "title": title,
            "raw": c.get("raw", ""),
            "source": source,
            "date_added": now,
            "status": "new",
        }
        existing.append(entry)
        existing_keys.add(key)
        added.append(entry)

    _save(existing, store_path)
    return {"added": added, "added_count": len(added), "skipped_count": skipped}


def update_status(entry_id: str, status: str, store_path: str = STORE_PATH) -> bool:
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status: {status!r}. Must be one of {sorted(VALID_STATUSES)}.")
    entries = _load(store_path)
    for entry in entries:
        if entry["id"] == entry_id:
            entry["status"] = status
            _save(entries, store_path)
            return True
    return False


def delete_entry(entry_id: str, store_path: str = STORE_PATH) -> bool:
    entries = _load(store_path)
    remaining = [e for e in entries if e["id"] != entry_id]
    if len(remaining) == len(entries):
        return False
    _save(remaining, store_path)
    return True


def build_discovery_log_csv(entries: list[dict]) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Artist", "Title", "Source", "Date Added", "Status"])
    for entry in entries:
        writer.writerow(
            [entry["artist"], entry["title"], entry["source"], entry["date_added"], entry["status"]]
        )
    return output.getvalue()
