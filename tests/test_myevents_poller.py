from unittest.mock import Mock, patch

import pytest

from crate_builder import local_config, myevents_poller, pending_store


def test_fetch_pending_raises_when_not_configured():
    with pytest.raises(myevents_poller.ShowfilePendingError):
        myevents_poller.fetch_pending()


def test_fetch_pending_gets_expected_request():
    local_config.update_settings(showfile_url="https://www.showfile.events", showfile_api_key="a-key")

    mock_response = Mock(ok=True, status_code=200)
    mock_response.json.return_value = {
        "events": [{"code": "ABC123", "couple": "Alex & Sam", "date": "2026-09-12", "songs": []}]
    }

    with patch("crate_builder.myevents_poller.requests.get", return_value=mock_response) as mock_get:
        events = myevents_poller.fetch_pending()

    assert events == [{"code": "ABC123", "couple": "Alex & Sam", "date": "2026-09-12", "songs": []}]
    mock_get.assert_called_once_with(
        "https://www.showfile.events/api/playlist/pending",
        headers={"Authorization": "Bearer a-key"},
        timeout=10,
    )


def test_fetch_pending_clears_key_on_401():
    local_config.update_settings(
        showfile_url="https://www.showfile.events", showfile_api_key="stale-key", showfile_business_name="DJ Test"
    )
    mock_response = Mock(ok=False, status_code=401)

    with patch("crate_builder.myevents_poller.requests.get", return_value=mock_response):
        with pytest.raises(myevents_poller.ShowfilePendingError):
            myevents_poller.fetch_pending()

    settings = local_config.get_settings()
    assert settings["showfile_api_key"] == ""
    assert settings["showfile_business_name"] == ""


def test_poll_once_updates_pending_store(tmp_path, monkeypatch):
    monkeypatch.setattr(pending_store, "STORE_PATH", str(tmp_path / "pending_events.json"))
    local_config.update_settings(showfile_url="https://www.showfile.events", showfile_api_key="a-key")

    mock_response = Mock(ok=True, status_code=200)
    mock_response.json.return_value = {
        "events": [{"code": "ABC123", "couple": "Alex & Sam", "date": "2026-09-12", "songs": [{"moment": "M1", "song": "S1"}]}]
    }

    with patch("crate_builder.myevents_poller.requests.get", return_value=mock_response):
        events = myevents_poller.poll_once()

    assert events[0]["songs"][0]["is_new"] is True
    assert pending_store.get_cached_events() == events
