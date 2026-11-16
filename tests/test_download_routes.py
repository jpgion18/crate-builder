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
