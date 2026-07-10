"""Build a downloadable CSV log of tracks that weren't found in the local library."""

from __future__ import annotations

import csv
import io


def build_missing_log_csv(missing_tracks: list[dict]) -> str:
    """missing_tracks: list of {"artist": ..., "title": ..., "raw": ...}."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Artist", "Title", "Original Input", "Notes"])
    for track in missing_tracks:
        writer.writerow(
            [track.get("artist", ""), track.get("title", ""), track.get("raw", ""), ""]
        )
    return output.getvalue()
