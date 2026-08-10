"""Local web app: paste a CSV / Spotify playlist / plain track list, fuzzy-match
it against your local music library, and build a Serato crate from the results.

Run with:
    python app.py
Then open http://127.0.0.1:5001 in your browser.
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, redirect, request, render_template

from crate_builder import discovery_store, local_config, serato_crate, serato_paths
from crate_builder.community_client import (
    CommunityAccessCodeMissing,
    CommunityNotConfigured,
    CommunityRequestError,
    list_crates,
    publish_crate,
)
from crate_builder.input_parser import parse_input_text
from crate_builder.library import scan_library
from crate_builder.matcher import DEFAULT_THRESHOLD, match_tracks, normalize
from crate_builder.missing_log import build_missing_log_csv
from crate_builder.showfile_client import ShowfileNotConfigured, ShowfileSyncError, sync_playlist
from crate_builder.spotify_client import (
    SpotifyNotConfigured,
    SpotifyNotConnected,
    fetch_playlist_tracks,
    get_login_url,
    handle_callback,
    is_connected,
    is_spotify_url,
)
from spotipy.exceptions import SpotifyException

load_dotenv()

# When packaged with PyInstaller, templates/static ship as extracted data
# files under sys._MEIPASS rather than next to this source file.
_BASE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))

app = Flask(
    __name__,
    template_folder=os.path.join(_BASE_DIR, "templates"),
    static_folder=os.path.join(_BASE_DIR, "static"),
)

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


def _resolve_input_tracks_safe(input_text: str):
    """Returns (tracks, None) on success, or (None, (message, status)) on a handled error."""
    try:
        return _resolve_input_tracks(input_text), None
    except (SpotifyNotConfigured, SpotifyNotConnected) as exc:
        return None, (str(exc), 400)
    except SpotifyException as exc:
        if exc.http_status == 403:
            message = (
                "Spotify refused to fetch that playlist (403 Forbidden). Make sure "
                "you're logged in as an account that can see this playlist (click "
                "'Connect Spotify' again if unsure), or paste the track list as "
                "plain text/CSV instead."
            )
        elif exc.http_status == 404:
            message = "Spotify couldn't find that playlist — double check the URL."
        else:
            message = f"Spotify API error ({exc.http_status}): {exc.msg}"
        return None, (message, 400)


def _showfile_configured() -> bool:
    settings = local_config.get_settings()
    url = settings["showfile_url"] or os.environ.get("SHOWFILE_API_URL", "")
    key = settings["showfile_api_key"] or os.environ.get("SHOWFILE_API_KEY", "")
    return bool(url and key)


def _community_configured() -> bool:
    settings = local_config.get_settings()
    url = settings["community_url"] or os.environ.get("COMMUNITY_API_URL", "")
    return bool(url)


@app.route("/")
def index():
    return render_template(
        "index.html",
        default_library_dir=serato_paths.guess_music_dir(),
        default_serato_dir=serato_paths.guess_serato_dir(),
        default_threshold=DEFAULT_THRESHOLD,
        showfile_configured=_showfile_configured(),
        community_configured=_community_configured(),
    )


@app.route("/discover")
def discover_page():
    return render_template(
        "discover.html",
        default_library_dir=serato_paths.guess_music_dir(),
        default_threshold=DEFAULT_THRESHOLD,
    )


@app.route("/community")
def community_page():
    return render_template("community.html")


@app.route("/settings")
def settings_page():
    return render_template("settings.html")


@app.route("/login")
def login():
    try:
        return redirect(get_login_url())
    except SpotifyNotConfigured as exc:
        return str(exc), 400


@app.route("/callback")
def callback():
    code = request.args.get("code")
    error = request.args.get("error")
    if error:
        return f"Spotify login failed: {error}", 400
    if not code:
        return "Spotify login failed: no authorization code received.", 400
    handle_callback(code)
    return redirect("/")


@app.route("/api/spotify-status")
def api_spotify_status():
    return jsonify(connected=is_connected())


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

    input_tracks, error = _resolve_input_tracks_safe(input_text)
    if error:
        return jsonify(error=error[0]), error[1]

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


@app.route("/api/discover/preview", methods=["POST"])
def api_discover_preview():
    data = request.get_json(force=True)
    library_dir = data.get("library_dir", "").strip()
    input_text = data.get("input_text", "")
    threshold = int(data.get("threshold", DEFAULT_THRESHOLD))

    if not library_dir:
        return jsonify(error="library_dir is required"), 400
    if not input_text.strip():
        return jsonify(error="Paste a tracklist, chart, or Spotify playlist URL first"), 400

    try:
        library_tracks = _get_library(library_dir)
    except NotADirectoryError as exc:
        return jsonify(error=str(exc)), 400

    input_tracks, error = _resolve_input_tracks_safe(input_text)
    if error:
        return jsonify(error=error[0]), error[1]

    if not input_tracks:
        return jsonify(error="Couldn't parse any tracks from that input"), 400

    results = match_tracks(input_tracks, library_tracks, threshold=threshold)
    logged_keys = {
        normalize(f"{e['artist']} {e['title']}") for e in discovery_store.list_entries()
    }

    candidates = [
        {
            "raw": r.input.raw,
            "artist": r.input.artist,
            "title": r.input.title,
            "in_library": r.matched,
            "already_logged": normalize(f"{r.input.artist} {r.input.title}") in logged_keys,
        }
        for r in results
    ]

    return jsonify(candidates=candidates)


@app.route("/api/discover/add", methods=["POST"])
def api_discover_add():
    data = request.get_json(force=True)
    entries = data.get("entries", [])
    source = data.get("source", "").strip() or "Unspecified"
    if not entries:
        return jsonify(error="No tracks selected"), 400
    result = discovery_store.add_entries(entries, source)
    return jsonify(result)


@app.route("/api/discover/list")
def api_discover_list():
    return jsonify(entries=discovery_store.list_entries())


@app.route("/api/discover/status", methods=["POST"])
def api_discover_status():
    data = request.get_json(force=True)
    entry_id = data.get("id", "")
    status = data.get("status", "")
    try:
        ok = discovery_store.update_status(entry_id, status)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    if not ok:
        return jsonify(error="Entry not found"), 404
    return jsonify(ok=True)


@app.route("/api/discover/<entry_id>", methods=["DELETE"])
def api_discover_delete(entry_id):
    ok = discovery_store.delete_entry(entry_id)
    if not ok:
        return jsonify(error="Entry not found"), 404
    return jsonify(ok=True)


@app.route("/api/discover/export")
def api_discover_export():
    entries = discovery_store.list_entries()
    if not entries:
        return jsonify(error="Discovery log is empty"), 400
    csv_text = discovery_store.build_discovery_log_csv(entries)
    return Response(
        csv_text,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=discovery_log.csv"},
    )


@app.route("/api/sync_showfile", methods=["POST"])
def api_sync_showfile():
    data = request.get_json(force=True)
    event_code = data.get("event_code", "").strip()
    tracks = data.get("tracks", [])

    if not event_code:
        return jsonify(error="Showfile event code is required"), 400
    if not tracks:
        return jsonify(error="No matched tracks to sync"), 400

    try:
        result = sync_playlist(event_code, tracks)
    except ShowfileNotConfigured as exc:
        return jsonify(error=str(exc)), 400
    except ShowfileSyncError as exc:
        return jsonify(error=str(exc)), exc.status_code or 502

    return jsonify(count=result.get("count", len(tracks)))


@app.route("/api/publish_crate", methods=["POST"])
def api_publish_crate():
    data = request.get_json(force=True)
    crate_name = data.get("crate_name", "").strip()
    tracks = data.get("tracks", [])
    tag = data.get("tag", "").strip()
    display_name = data.get("display_name", "").strip()

    if not crate_name:
        return jsonify(error="crate_name is required"), 400
    if not tracks:
        return jsonify(error="No tracks to publish"), 400

    try:
        result = publish_crate(crate_name, tracks, tag=tag, display_name=display_name)
    except (CommunityNotConfigured, CommunityAccessCodeMissing) as exc:
        return jsonify(error=str(exc)), 400
    except CommunityRequestError as exc:
        return jsonify(error=str(exc)), exc.status_code or 502

    return jsonify(result)


@app.route("/api/community/list", methods=["GET"])
def api_community_list():
    query = request.args.get("q", "")
    limit = int(request.args.get("limit", 20))
    offset = int(request.args.get("offset", 0))

    try:
        result = list_crates(query=query, limit=limit, offset=offset)
    except (CommunityNotConfigured, CommunityAccessCodeMissing) as exc:
        return jsonify(error=str(exc)), 400
    except CommunityRequestError as exc:
        return jsonify(error=str(exc)), exc.status_code or 502

    return jsonify(result)


@app.route("/api/settings", methods=["GET"])
def api_settings_get():
    settings = local_config.get_settings()
    return jsonify(
        **settings,
        showfile_configured=_showfile_configured(),
        community_configured=_community_configured(),
    )


@app.route("/api/settings", methods=["POST"])
def api_settings_post():
    data = request.get_json(force=True)
    updates = {
        key: data[key]
        for key in ("showfile_url", "showfile_api_key", "community_url", "community_access_code")
        if key in data
    }
    settings = local_config.update_settings(**updates)
    return jsonify(**settings)


if __name__ == "__main__":
    # Port 5000 is reserved by macOS AirPlay Receiver and will silently
    # 403 requests before they reach Flask, so default to 5001 instead.
    app.run(debug=True, port=5001)
