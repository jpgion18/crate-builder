"""Background batch runner for the MusicBrainz year-checker: works through
a Serato database's tracks one at a time, respecting MusicBrainz's real
1-request/second rate limit. This runs server-side (see musicbrainz_client),
so there's no CORS proxy involved and no artificially tighter pace to work
around like the browser-based concept prototype needed.

Tracks already checked in a previous run (yearcheck_store) are skipped
automatically — that's what makes stopping and resuming a check across app
restarts work without a manual export/reload step, for a library large
enough that a full pass can take hours.
"""

from __future__ import annotations

import threading
import time

from crate_builder import musicbrainz_client, serato_database, yearcheck_store

MUSICBRAINZ_PACE_SECONDS = 1.1  # MusicBrainz's real limit is 1 req/sec; a little headroom

_state_lock = threading.Lock()
_state = {
    "status": "idle",  # idle | running | stopped
    "total": 0,
    "checked": 0,
    "current": "",
}
_stop_requested = False


class YearCheckError(RuntimeError):
    pass


def get_status() -> dict:
    with _state_lock:
        return dict(_state)


def stop() -> None:
    global _stop_requested
    _stop_requested = True


def start(database_path: str, limit: int | None = None) -> None:
    """Fire-and-forget: spawns the background thread once the database has
    been read and any already-running check ruled out. Raises YearCheckError
    synchronously for either problem, before anything starts, rather than
    only surfacing on the next status poll."""
    global _stop_requested

    with _state_lock:
        if _state["status"] == "running":
            raise YearCheckError("A year check is already running.")

    tracks = serato_database.parse_database(database_path)
    to_check = [t for t in tracks if not yearcheck_store.is_checked(t.artist, t.title)]
    if limit is not None:
        to_check = to_check[:limit]

    _stop_requested = False
    with _state_lock:
        _state["status"] = "running"
        _state["total"] = len(to_check)
        _state["checked"] = 0
        _state["current"] = ""

    threading.Thread(target=_run, args=(to_check,), daemon=True).start()


def _run(tracks: list) -> None:
    for track in tracks:
        if _stop_requested:
            break

        with _state_lock:
            _state["current"] = f"{track.artist} — {track.title}"

        result = musicbrainz_client.lookup_year(track.artist, track.title)
        tag_year = (track.year or "").strip()
        if result["status"] == "matched":
            result["status"] = "match" if tag_year and tag_year == result["mb_year"] else "mismatch"
        result.update({"path": track.path, "artist": track.artist, "title": track.title, "tag_year": tag_year})
        yearcheck_store.save_result(track.artist, track.title, result)

        with _state_lock:
            _state["checked"] += 1

        time.sleep(MUSICBRAINZ_PACE_SECONDS)

    with _state_lock:
        _state["status"] = "stopped" if _stop_requested else "idle"
        _state["current"] = ""
