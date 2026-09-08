"""Build a downloadable CSV of a Spotify playlist's per-track year/genre,
for eyeballing what era/genre mix a client's playlist is actually made of.
"""

from __future__ import annotations

import csv
import io


def build_year_genre_csv(tracks: list[dict]) -> str:
    """tracks: list of {"artist": ..., "title": ..., "year": ..., "genres": ...}."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Artist", "Title", "Year", "Genres"])
    for track in tracks:
        writer.writerow(
            [track.get("artist", ""), track.get("title", ""), track.get("year", ""), track.get("genres", "")]
        )
    return output.getvalue()


def summarize_year_genre(tracks: list[dict]) -> dict:
    """Counts how many tracks fall into each decade and each genre, for an
    at-a-glance read on what a playlist's era/genre mix actually is without
    opening the CSV in a spreadsheet.

    Returns {"by_decade": [(label, count), ...], "by_genre": [(genre, count),
    ...]}, both sorted biggest bucket first (ties broken alphabetically). A
    track missing a year or genre counts toward an explicit "Unknown"
    bucket rather than being silently dropped, so the totals stay honest
    about how much data is actually missing. Genres are comma-joined (an
    artist can have several) — each one counts toward its own bucket, so a
    "pop, dance pop" track adds one to *both*, not one to a combined
    "pop, dance pop" bucket.
    """
    decade_counts: dict[str, int] = {}
    genre_counts: dict[str, int] = {}

    for track in tracks:
        decade = _decade_label(track.get("year", ""))
        decade_counts[decade] = decade_counts.get(decade, 0) + 1

        genres = [g.strip() for g in (track.get("genres") or "").split(",") if g.strip()]
        if not genres:
            genre_counts["Unknown"] = genre_counts.get("Unknown", 0) + 1
        else:
            for genre in genres:
                genre_counts[genre] = genre_counts.get(genre, 0) + 1

    return {
        "by_decade": sorted(decade_counts.items(), key=lambda kv: (-kv[1], kv[0])),
        "by_genre": sorted(genre_counts.items(), key=lambda kv: (-kv[1], kv[0])),
    }


def _decade_label(year: str) -> str:
    if not year or not year.isdigit():
        return "Unknown"
    decade_start = (int(year) // 10) * 10
    return f"{decade_start}s"
