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
