"""POST-built downloads (Rekordbox XML, CSV logs) must survive pywebview's re-fetch.

On macOS, pywebview cancels a download response, shows the Save dialog, then
fetches the same URL again with a plain GET and no form body. A POST-only route
answered that with 405, and the "Method Not Allowed" page was saved as the file.
"""

from __future__ import annotations

import json

import pytest

import app as app_module
from app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    app_module._DOWNLOADS.clear()
    return app.test_client()


def _post_then_refetch(client, url: str, form: dict):
    res = client.post(url, data=form)
    assert res.status_code == 303, res.get_data(as_text=True)
    location = res.headers["Location"]
    assert "/api/download/" in location
    # The webview's own GET, then pywebview's separate re-fetch: both must work.
    first = client.get(location)
    second = client.get(location)
    for got in (first, second):
        assert got.status_code == 200
        assert got.mimetype == "application/octet-stream"
        assert "attachment" in got.headers["Content-Disposition"]
    assert first.get_data() == second.get_data()
    return second


def test_missing_log_download_survives_refetch(client) -> None:
    tracks = [{"artist": "Lascala", "title": "Fire"}]
    res = _post_then_refetch(client, "/api/missing-log", {"tracks_json": json.dumps(tracks)})
    assert "missing_tracks.csv" in res.headers["Content-Disposition"]
    assert b"Fire" in res.get_data()


def test_year_genre_log_download_survives_refetch(client) -> None:
    tracks = [{"artist": "Lascala", "title": "Fire", "year": "2024", "genre": "house"}]
    res = _post_then_refetch(client, "/api/spotify/year-genre-log", {"tracks_json": json.dumps(tracks)})
    assert "year_genre_breakdown.csv" in res.headers["Content-Disposition"]


def test_errors_still_come_back_directly(client) -> None:
    res = client.post("/api/missing-log", data={"tracks_json": "[]"})
    assert res.status_code == 400


def test_unknown_or_expired_download_is_404(client, monkeypatch) -> None:
    assert client.get("/api/download/nope").status_code == 404
    res = client.post("/api/missing-log", data={"tracks_json": json.dumps([{"artist": "A", "title": "B"}])})
    location = res.headers["Location"]
    real_time = app_module.time.time
    monkeypatch.setattr(app_module.time, "time", lambda: real_time() + app_module._DOWNLOAD_TTL_SECONDS + 1)
    assert client.get(location).status_code == 404


# static/download.js asks for JSON, then the packaged app saves the file
# itself (desktop_app.SaveApi) instead of letting pywebview re-fetch a URL.
# That re-fetch is what saved the "405 Method Not Allowed" page on macOS.


def _post_for_token(client, url: str, form: dict) -> dict:
    res = client.post(url, data=form, headers={"Accept": "application/json"})
    assert res.status_code == 200, res.get_data(as_text=True)
    body = res.get_json()
    assert body["url"] == f"/api/download/{body['token']}"
    return body


def test_json_mode_returns_token_for_the_stored_file(client) -> None:
    tracks = [{"artist": "Lascala", "title": "Fire"}]
    body = _post_for_token(client, "/api/missing-log", {"tracks_json": json.dumps(tracks)})
    assert body["filename"] == "missing_tracks.csv"
    data, filename = app_module.get_download(body["token"])
    assert filename == "missing_tracks.csv"
    assert b"Fire" in data
    # The browser path (python app.py) still loads it by URL.
    assert client.get(body["url"]).get_data() == data


def test_json_mode_errors_come_back_as_json(client) -> None:
    res = client.post("/api/missing-log", data={"tracks_json": "[]"}, headers={"Accept": "application/json"})
    assert res.status_code == 400
    assert res.get_json()["error"]


class _FakeWindow:
    def __init__(self, chosen):
        self.chosen = chosen
        self.asked = None

    def create_file_dialog(self, dialog_type, directory="", save_filename=""):
        self.asked = (dialog_type, save_filename)
        return self.chosen


@pytest.mark.parametrize("shape", [str, lambda p: (p,)])  # str on macOS, tuple on Windows
def test_desktop_save_writes_the_real_file(client, tmp_path, shape) -> None:
    webview = pytest.importorskip("webview")
    import desktop_app

    tracks = [{"artist": "Lascala", "title": "Fire"}]
    body = _post_for_token(client, "/api/missing-log", {"tracks_json": json.dumps(tracks)})
    dest = tmp_path / "out.csv"
    api = desktop_app.SaveApi()
    api._window = _FakeWindow(shape(str(dest)))

    assert api.save_download(body["token"]) == {"saved": str(dest)}
    assert api._window.asked == (webview.SAVE_DIALOG, "missing_tracks.csv")
    assert dest.read_bytes() == app_module.get_download(body["token"])[0]
    assert b"Method Not Allowed" not in dest.read_bytes()


def test_desktop_save_cancelled_and_expired(client) -> None:
    pytest.importorskip("webview")
    import desktop_app

    api = desktop_app.SaveApi()
    api._window = _FakeWindow(None)
    assert api.save_download("nope") == {"error": "This download has expired. Export it again."}
    body = _post_for_token(client, "/api/missing-log", {"tracks_json": json.dumps([{"artist": "A", "title": "B"}])})
    assert api.save_download(body["token"]) == {"cancelled": True}


def test_desktop_api_exposes_only_save_download() -> None:
    pytest.importorskip("webview")
    import desktop_app

    public = [n for n in dir(desktop_app.SaveApi()) if not n.startswith("_")]
    assert public == ["save_download"]
