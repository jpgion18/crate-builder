import pytest

from crate_builder import local_config


def test_get_settings_defaults_to_empty_strings():
    settings = local_config.get_settings()
    assert settings == {
        "showfile_url": "",
        "showfile_api_key": "",
        "showfile_business_name": "",
        "community_url": "",
        "community_access_code": "",
    }


def test_update_settings_round_trip():
    local_config.update_settings(showfile_url="  https://www.showfile.events  ", showfile_api_key="abc-123")
    settings = local_config.get_settings()
    assert settings["showfile_url"] == "https://www.showfile.events"
    assert settings["showfile_api_key"] == "abc-123"
    assert settings["community_url"] == ""


def test_update_settings_only_touches_given_keys():
    local_config.update_settings(showfile_url="https://www.showfile.events")
    local_config.update_settings(showfile_api_key="abc-123")
    settings = local_config.get_settings()
    assert settings["showfile_url"] == "https://www.showfile.events"
    assert settings["showfile_api_key"] == "abc-123"


def test_update_settings_rejects_unknown_key():
    with pytest.raises(ValueError):
        local_config.update_settings(not_a_real_setting="x")


def test_get_rejects_unknown_key():
    with pytest.raises(ValueError):
        local_config.get("not_a_real_setting")
