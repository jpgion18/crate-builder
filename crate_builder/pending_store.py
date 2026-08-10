"""Local cache of Showfile's pending-songs poll (GET /api/playlist/pending),
plus a "seen" snapshot to diff against so the MyEvents tab can flag which
songs are new since the last poll. Showfile's endpoint is stateless —
always full current state, never a delta — so this snapshot is what makes
"new" mean anything at all.
"""

from __future__ import annotations

import json
import os

STORE_PATH = os.path.join(os.path.expanduser("~"), ".crate_builder", "pending_events.json")


def _song_key(moment: str, song: str) -> str:
    return f"{moment}\x1f{song}"


def _load() -> dict:
    try:
        with open(STORE_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {"events": [], "seen": {}}


def _save(data: dict) -> None:
    os.makedirs(os.path.dirname(STORE_PATH), exist_ok=True)
    with open(STORE_PATH, "w") as f:
        json.dump(data, f, indent=2)


def get_cached_events() -> list[dict]:
    """Events (with each song tagged is_new) as of the last poll — doesn't
    itself call Showfile, safe to call on every page load."""
    return _load()["events"]


def update_from_poll(events: list[dict]) -> list[dict]:
    """Call with the raw `events` list from GET /api/playlist/pending.
    Diffs each event's songs against what was seen on the previous poll,
    tags each song is_new, saves the new snapshot, and returns the tagged
    events (also what get_cached_events() returns until the next poll).
    """
    previous_seen = _load().get("seen", {})

    tagged_events = []
    new_seen = {}
    for event in events:
        code = event["code"]
        previously_seen_keys = set(previous_seen.get(code, []))
        songs = event.get("songs", [])
        new_seen[code] = [_song_key(s["moment"], s["song"]) for s in songs]

        tagged_events.append(
            {
                **event,
                "songs": [
                    {**s, "is_new": _song_key(s["moment"], s["song"]) not in previously_seen_keys}
                    for s in songs
                ],
            }
        )

    _save({"events": tagged_events, "seen": new_seen})
    return tagged_events
