"""Local web app: paste a CSV / Spotify playlist / plain track list, fuzzy-match
it against your local music library, and build a Serato crate from the results.

Run with:
    python app.py
Then open http://127.0.0.1:5001 in your browser.
"""

from __future__ import annotations

import json
import os
import sys
import webbrowser
from urllib.parse import urlencode

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, redirect, request, render_template

from crate_builder import discovery_store, local_config, pending_store, serato_crate, serato_paths
from crate_builder.community_client import (
    CommunityAccessCodeMissing,
    CommunityNotConfigured,
    CommunityRequestError,
    list_crates,
    publish_crate,
)
from crate_builder.duplicates import find_duplicates
from crate_builder.input_parser import parse_input_text
from crate_builder.library import scan_library
from crate_builder.matcher import DEFAULT_THRESHOLD, match_tracks, normalize
from crate_builder.metadata_editor import (
    MetadataError,
    list_backups,
    read_tags,
    restore_backup,
    write_tags,
)
from crate_builder.missing_log import build_missing_log_csv
from crate_builder.myevents_poller import ShowfilePendingError, poll_once, start_background_polling
from crate_builder.showfile_auth import ShowfileAuthError, exchange_code, resolved_base_url, start_login
from crate_builder.showfile_client import ShowfileNotConfigured, ShowfileSyncError, sync_playlist
from crate_builder.version import get_version
from crate_builder.spotify_client import (
    SpotifyLoginExpired,
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
APP_VERSION = get_version(_BASE_DIR)

app = Flask(
    __name__,
    template_folder=os.path.join(_BASE_DIR, "templates"),
    static_folder=os.path.join(_BASE_DIR, "static"),
)

# Single-user local tool: an in-memory cache keyed by library directory is
# enough to avoid re-scanning the whole library on every request.
_LIBRARY_CACHE: dict[str, list] = {}

# Pending "Log in with Showfile" attempts: state -> (code_verifier, redirect_uri).
# In-memory is fine — single-user, single-process, and an entry only lives
# between /showfile/login and /showfile/callback a few seconds later.
_SHOWFILE_AUTH_PENDING: dict[str, tuple[str, str]] = {}


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


@app.route("/library")
def library_page():
    return render_template("library.html", default_library_dir=serato_paths.guess_music_dir())


@app.route("/myevents")
def myevents_page():
    return render_template("myevents.html")


@app.route("/settings")
def settings_page():
    return render_template("settings.html")


@app.route("/login")
def login():
    try:
        authorize_url = get_login_url()
    except SpotifyNotConfigured as exc:
        return str(exc), 400
    # Opened in the system browser rather than navigated in-place, same
    # reasoning as Showfile login below: reliable regardless of whether
    # this is running as `python app.py` or inside the packaged desktop
    # app's embedded window.
    webbrowser.open(authorize_url)
    return redirect("/?spotify_pending=1")


@app.route("/callback")
def callback():
    code = request.args.get("code")
    error = request.args.get("error")
    state = request.args.get("state", "")
    if error:
        return redirect(f"/?{urlencode({'spotify_error': error})}")
    if not code:
        return redirect(f"/?{urlencode({'spotify_error': 'no authorization code received'})}")
    try:
        handle_callback(code, state)
    except SpotifyLoginExpired as exc:
        return redirect(f"/?{urlencode({'spotify_error': str(exc)})}")
    return redirect("/")


@app.route("/showfile/login")
def showfile_login():
    redirect_uri = request.host_url.rstrip("/") + "/showfile/callback"
    authorize_url, state, code_verifier = start_login(redirect_uri)
    _SHOWFILE_AUTH_PENDING[state] = (code_verifier, redirect_uri)
    # Showfile login is magic-link email based: if this navigated inside
    # the packaged app's embedded window (pywebview) rather than the
    # system browser, clicking the emailed link would open a *different*
    # window than the one waiting for the callback, stranding the flow.
    # Opening the system browser explicitly avoids that regardless of
    # whether crate-builder is running as `python app.py` or packaged.
    webbrowser.open(authorize_url)
    return redirect("/settings?showfile_pending=1")


@app.route("/showfile/callback")
def showfile_callback():
    error = request.args.get("error")
    state = request.args.get("state", "")
    code = request.args.get("code")

    pending = _SHOWFILE_AUTH_PENDING.pop(state, None)
    if error:
        return redirect(f"/settings?{urlencode({'showfile_error': error})}")
    if not pending:
        return "Showfile login failed: missing or expired state.", 400
    if not code:
        return "Showfile login failed: no authorization code received.", 400

    code_verifier, redirect_uri = pending
    try:
        result = exchange_code(code, code_verifier, redirect_uri)
    except ShowfileAuthError as exc:
        return redirect(f"/settings?{urlencode({'showfile_error': str(exc)})}")

    updates = {
        "showfile_api_key": result.get("api_key", ""),
        "community_access_code": result.get("crate_builder_code", ""),
        "showfile_business_name": result.get("business_name", ""),
    }
    # Login only ever talks to Showfile, so it can't tell us a Community
    # feed URL — but the whole point of this flow is "one login enables
    # both features" (per Settings' own copy), so default it here too
    # rather than leaving community_configured false until a manual save.
    current = local_config.get_settings()
    if not current["showfile_url"]:
        updates["showfile_url"] = resolved_base_url()
    if not current["community_url"]:
        updates["community_url"] = os.environ.get("COMMUNITY_API_URL", "").strip() or "https://crate.showfile.events"
    local_config.update_settings(**updates)
    return redirect("/settings")


@app.route("/api/showfile/disconnect", methods=["POST"])
def api_showfile_disconnect():
    local_config.update_settings(showfile_api_key="", community_access_code="", showfile_business_name="")
    return jsonify(ok=True)


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


@app.route("/api/duplicates", methods=["POST"])
def api_duplicates():
    data = request.get_json(force=True)
    library_dir = data.get("library_dir", "").strip()
    if not library_dir:
        return jsonify(error="library_dir is required"), 400
    try:
        library_tracks = _get_library(library_dir)
    except NotADirectoryError as exc:
        return jsonify(error=str(exc)), 400

    groups = find_duplicates(library_tracks)
    return jsonify(
        groups=[
            {
                "reason": g.reason,
                "tracks": [
                    {"path": t.path, "artist": t.artist, "title": t.title, "album": t.album}
                    for t in g.tracks
                ],
            }
            for g in groups
        ]
    )


@app.route("/api/metadata", methods=["GET"])
def api_metadata_get():
    path = request.args.get("path", "")
    try:
        tags = read_tags(path)
    except MetadataError as exc:
        return jsonify(error=str(exc)), 400
    return jsonify(tags=tags)


@app.route("/api/metadata", methods=["POST"])
def api_metadata_post():
    data = request.get_json(force=True)
    path = data.get("path", "")
    fields = data.get("fields", {})
    try:
        backup_path = write_tags(path, fields)
    except MetadataError as exc:
        return jsonify(error=str(exc)), 400
    # The scanned library cache now has this track's stale tags — clear it
    # so the next scan-dependent call (preview, search, duplicates) picks
    # up what was actually just written, rather than showing an edit that
    # silently didn't seem to take effect anywhere else in the app.
    _LIBRARY_CACHE.clear()
    return jsonify(ok=True, backup_path=backup_path)


@app.route("/api/metadata/backups", methods=["GET"])
def api_metadata_backups():
    return jsonify(backups=list_backups())


@app.route("/api/metadata/restore", methods=["POST"])
def api_metadata_restore():
    data = request.get_json(force=True)
    backup_path = data.get("backup_path", "")
    try:
        restore_backup(backup_path)
    except MetadataError as exc:
        return jsonify(error=str(exc)), 400
    _LIBRARY_CACHE.clear()
    return jsonify(ok=True)


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
    # Submitted as a real HTML form (not fetch()) so the response's
    # Content-Disposition: attachment header triggers a genuine top-level
    # navigation the browser/webview handles as a native file download,
    # rather than JS building a blob: URL and clicking a synthetic <a
    # download> link — that pattern is known to just display the blob's
    # raw content in place instead of downloading it inside the packaged
    # desktop app's embedded webview (pywebview), with no way back.
    tracks_json = request.form.get("tracks_json")
    tracks = json.loads(tracks_json) if tracks_json else []
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
        app_version=APP_VERSION,
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


@app.route("/api/myevents", methods=["GET"])
def api_myevents():
    """Serves the local cache from the last poll — never calls Showfile
    itself, so loading this page has no rate-limit cost."""
    return jsonify(events=pending_store.get_cached_events())


@app.route("/api/myevents/refresh", methods=["POST"])
def api_myevents_refresh():
    try:
        events = poll_once()
    except ShowfilePendingError as exc:
        return jsonify(error=str(exc)), 502
    return jsonify(events=events)


if __name__ == "__main__":
    # debug=True below runs under Werkzeug's reloader, which re-execs this
    # script in a child process (setting WERKZEUG_RUN_MAIN=true there) and
    # keeps the original as a file-watching monitor that never serves.
    # Since this whole __main__ block reruns in both, only start polling
    # in the child that's actually going to serve — otherwise two
    # processes would each run their own polling loop.
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        start_background_polling()
    # Port 5000 is reserved by macOS AirPlay Receiver and will silently
    # 403 requests before they reach Flask, so default to 5001 instead.
    app.run(debug=True, port=5001)
