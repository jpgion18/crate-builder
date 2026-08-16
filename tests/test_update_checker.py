from unittest.mock import Mock, patch

import pytest

from crate_builder import update_checker


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(update_checker, "CACHE_PATH", str(tmp_path / "update_check.json"))


def _mock_release(tag_name="v0.9.0", html_url="https://github.com/jpgion18/crate-builder/releases/tag/v0.9.0"):
    resp = Mock()
    resp.ok = True
    resp.json.return_value = {"tag_name": tag_name, "html_url": html_url}
    return resp


def test_dev_version_never_reports_an_update():
    with patch("crate_builder.update_checker.requests.get", return_value=_mock_release()) as mock_get:
        result = update_checker.check_for_update("dev")
    assert result["update_available"] is False
    mock_get.assert_not_called()


def test_empty_version_never_reports_an_update():
    result = update_checker.check_for_update("")
    assert result["update_available"] is False


def test_reports_update_when_latest_differs():
    with patch("crate_builder.update_checker.requests.get", return_value=_mock_release("v0.9.0")):
        result = update_checker.check_for_update("v0.8.0")
    assert result["update_available"] is True
    assert result["latest_version"] == "v0.9.0"
    assert result["release_url"] == "https://github.com/jpgion18/crate-builder/releases/tag/v0.9.0"


def test_no_update_when_already_current():
    with patch("crate_builder.update_checker.requests.get", return_value=_mock_release("v0.8.0")):
        result = update_checker.check_for_update("v0.8.0")
    assert result["update_available"] is False


def test_no_crash_on_network_failure_with_empty_cache():
    with patch("crate_builder.update_checker.requests.get", side_effect=Exception("offline")):
        result = update_checker.check_for_update("v0.8.0")
    assert result["update_available"] is False


def test_falls_back_to_stale_cache_on_fetch_failure():
    with patch("crate_builder.update_checker.requests.get", return_value=_mock_release("v0.9.0")):
        first = update_checker.check_for_update("v0.8.0", force=True)
    assert first["update_available"] is True

    with patch("crate_builder.update_checker.requests.get", side_effect=Exception("offline")):
        second = update_checker.check_for_update("v0.8.0", force=True)
    assert second["update_available"] is True
    assert second["latest_version"] == "v0.9.0"


def test_second_call_within_interval_does_not_refetch():
    with patch("crate_builder.update_checker.requests.get", return_value=_mock_release("v0.9.0")) as mock_get:
        update_checker.check_for_update("v0.8.0")
        update_checker.check_for_update("v0.8.0")
    assert mock_get.call_count == 1


def test_force_bypasses_the_cache_interval():
    with patch("crate_builder.update_checker.requests.get", return_value=_mock_release("v0.9.0")) as mock_get:
        update_checker.check_for_update("v0.8.0")
        update_checker.check_for_update("v0.8.0", force=True)
    assert mock_get.call_count == 2


def test_http_error_status_is_treated_as_failure():
    resp = Mock()
    resp.ok = False
    with patch("crate_builder.update_checker.requests.get", return_value=resp):
        result = update_checker.check_for_update("v0.8.0")
    assert result["update_available"] is False


def test_download_url_points_at_the_macos_zip_on_darwin(monkeypatch):
    monkeypatch.setattr(update_checker.sys, "platform", "darwin")
    with patch("crate_builder.update_checker.requests.get", return_value=_mock_release("v0.9.0")):
        result = update_checker.check_for_update("v0.8.0")
    assert result["download_url"] == (
        "https://github.com/jpgion18/crate-builder/releases/latest/download/CrateBuilder-macos.zip"
    )


def test_download_url_points_at_the_windows_zip_on_win32(monkeypatch):
    monkeypatch.setattr(update_checker.sys, "platform", "win32")
    with patch("crate_builder.update_checker.requests.get", return_value=_mock_release("v0.9.0")):
        result = update_checker.check_for_update("v0.8.0")
    assert result["download_url"] == (
        "https://github.com/jpgion18/crate-builder/releases/latest/download/CrateBuilder-windows.zip"
    )


def test_download_url_is_none_on_an_unsupported_platform(monkeypatch):
    monkeypatch.setattr(update_checker.sys, "platform", "linux")
    with patch("crate_builder.update_checker.requests.get", return_value=_mock_release("v0.9.0")):
        result = update_checker.check_for_update("v0.8.0")
    assert result["update_available"] is True
    assert result["download_url"] is None


def test_no_update_result_always_has_a_download_url_key():
    result = update_checker.check_for_update("dev")
    assert "download_url" in result
    assert result["download_url"] is None


def test_stale_cache_older_than_current_version_is_not_an_update():
    # Reproduces the real bug: check for updates while still on v0.9.0
    # (caches "v0.9.1" as latest), then jump straight to installing v0.9.2
    # before the 24h cache expires. The stale cached v0.9.1 must not read
    # as an "update" now that v0.9.2 is actually running.
    with patch("crate_builder.update_checker.requests.get", return_value=_mock_release("v0.9.1")):
        update_checker.check_for_update("v0.9.0", force=True)

    result = update_checker.check_for_update("v0.9.2")
    assert result["update_available"] is False


def test_numeric_comparison_not_lexicographic():
    # "v0.10.0" < "v0.9.0" as plain strings, but is actually newer — a
    # naive string/lexicographic comparison would get this backwards.
    with patch("crate_builder.update_checker.requests.get", return_value=_mock_release("v0.10.0")):
        result = update_checker.check_for_update("v0.9.0", force=True)
    assert result["update_available"] is True


def test_non_semver_tags_fall_back_to_simple_inequality():
    assert update_checker._is_newer("nightly-build", "v0.9.0") is True
    assert update_checker._is_newer("v0.9.0", "v0.9.0") is False
