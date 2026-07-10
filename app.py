"""Local web app: paste a CSV / Spotify playlist / plain track list, fuzzy-match
it against your local music library, and build a Serato crate from the results.

Run with:
    python app.py
Then open http://127.0.0.1:5000 in your browser.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, request, render_template

from crate_builder import serato_crate, serato_paths
from crate_builder.input_parser import parse_input_text
from crate_builder.library import scan_library
from crate_builder.matcher import DEFAULT_THRESHOLD, match_tracks
from crate_builder.missing_log import build_missing_log_csv
from crate_builder.spotify_client import (
    SpotifyNotConfigured,
    fetch_playlist_tracks,
    is_spotify_url,
)
from spotipy.exceptions import SpotifyException

load_dotenv()

app = Flask(__name__)

# Single-user local tool: an in-memory cache keyed by library directory is
# enough to avoid re-scanning the whole library on every request.
_LIBRARY_CACHE: dict[str, list] = {}


def _get_library(library_dir: str, rescan: bool = False):
    library_dir = os.path.expanduser(library_dir)
    if rescan or library_dir not in _LIBRARY_CACHE:
        _LIBRARY_CACHE.clear()
        _LIBRARY_CACHE[library_dir] = scan_library(library_dir)
    return _LIBRARY_CACHE[library_dir]


def _resolve_input_tracks(input_text: str):
    input_text = input_text.strip()
    if is_spotify_url(input_text):
        return fetch_playlist_tracks(input_text)
    return parse_input_text(input_text)


@app.route("/")
def index():
    return render_template(
        "index.html",
        default_library_dir=serato_paths.guess_music_dir(),
        default_serato_dir=serato_paths.guess_serato_dir(),
        default_threshold=DEFAULT_THRESHOLD,
    )


@app.route("/api/scan", methods=["POST"])
def api_scan():
    data = request.get_json(force=True)
    library_dir = data.get("library_dir", "").strip()
    if not library_dir:
        return jsonify(error="library_dir is required"), 400
    try:
        tracks = _get_library(library_dir, rescan=True)
    except NotADirectoryError as exc:
        return jsonify(error=str(exc)), 400
    return jsonify(track_count=len(tracks))


@app.route("/api/preview", methods=["POST"])
def api_preview():
    data = request.get_json(force=True)
    library_dir = data.get("library_dir", "").strip()
    input_text = data.get("input_text", "")
    threshold = int(data.get("threshold", DEFAULT_THRESHOLD))

    if not library_dir:
        return jsonify(error="library_dir is required"), 400
    if not input_text.strip():
        return jsonify(error="Paste a CSV, Spotify playlist URL, or track list first"), 400

    try:
        library_tracks = _get_library(library_dir)
    except NotADirectoryError as exc:
        return jsonify(error=str(exc)), 400

    try:
        input_tracks = _resolve_input_tracks(input_text)
    except SpotifyNotConfigured as exc:
        return jsonify(error=str(exc)), 400
    except SpotifyException as exc:
        if exc.http_status == 403:
            message = (
                "Spotify refused to fetch that playlist (403 Forbidden). This app "
                "can only read PUBLIC playlists. Open the playlist in Spotify, "
                "check its sharing settings, and make sure it's set to Public "
                "(not private) — or paste the track list as plain text/CSV instead."
            )
        elif exc.http_status == 404:
            message = "Spotify couldn't find that playlist — double check the URL."
        else:
            message = f"Spotify API error ({exc.http_status}): {exc.msg}"
        return jsonify(error=message), 400

    if not input_tracks:
        return jsonify(error="Couldn't parse any tracks from that input"), 400

    results = match_tracks(input_tracks, library_tracks, threshold=threshold)

    matches = [
        {
            "raw": r.input.raw,
            "input_artist": r.input.artist,
            "input_title": r.input.title,
            "matched": r.matched,
            "score": round(r.score, 1),
            "track": (
                {
                    "path": r.track.path,
                    "artist": r.track.artist,
                    "title": r.track.title,
                    "album": r.track.album,
                }
                if r.track
                else None
            ),
        }
        for r in results
    ]

    return jsonify(
        library_count=len(library_tracks),
        input_count=len(input_tracks),
        matched_count=sum(1 for m in matches if m["matched"]),
        matches=matches,
    )


@app.route("/api/search", methods=["GET"])
def api_search():
    """Manual override lookup: top fuzzy candidates for a single free-text query."""
    from rapidfuzz import fuzz, process

    from crate_builder.matcher import normalize

    library_dir = request.args.get("library_dir", "").strip()
    query = request.args.get("q", "").strip()
    if not library_dir or not query:
        return jsonify(results=[])

    try:
        library_tracks = _get_library(library_dir)
    except NotADirectoryError as exc:
        return jsonify(error=str(exc)), 400

    choices = {i: normalize(f"{t.artist} {t.title}") for i, t in enumerate(library_tracks)}
    top = process.extract(normalize(query), choices, scorer=fuzz.WRatio, limit=5)
    results = [
        {
            "path": library_tracks[idx].path,
            "artist": library_tracks[idx].artist,
            "title": library_tracks[idx].title,
            "score": round(score, 1),
        }
        for _, score, idx in top
    ]
    return jsonify(results=results)


@app.route("/api/build", methods=["POST"])
def api_build():
    data = request.get_json(force=True)
    serato_dir = data.get("serato_dir", "").strip()
    crate_name = data.get("crate_name", "").strip()
    track_paths = data.get("track_paths", [])
    overwrite = bool(data.get("overwrite", False))

    if not serato_dir:
        return jsonify(error="serato_dir is required"), 400
    if not track_paths:
        return jsonify(error="No tracks selected to add to the crate"), 400

    try:
        filename = serato_paths.sanitize_crate_name(crate_name)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400

    dest_path = os.path.join(serato_paths.subcrates_dir(os.path.expanduser(serato_dir)), filename)

    try:
        serato_crate.write_crate(dest_path, track_paths, overwrite=overwrite)
    except FileExistsError:
        return jsonify(error="exists", path=dest_path), 409

    return jsonify(path=dest_path, track_count=len(track_paths))


@app.route("/api/missing-log", methods=["POST"])
def api_missing_log():
    data = request.get_json(force=True)
    tracks = data.get("tracks", [])
    if not tracks:
        return jsonify(error="No missing tracks to log"), 400

    csv_text = build_missing_log_csv(tracks)
    return Response(
        csv_text,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=missing_tracks.csv"},
    )


if __name__ == "__main__":
    # Port 5000 is reserved by macOS AirPlay Receiver and will silently
    # 403 requests before they reach Flask, so default to 5001 instead.
    app.run(debug=True, port=5001)
