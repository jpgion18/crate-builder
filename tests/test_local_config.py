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


def test_preference_round_trip_and_default():
    assert local_config.get_preference("build_target", "serato") == "serato"
    local_config.set_preference("build_target", "rekordbox")
    assert local_config.get_preference("build_target", "serato") == "rekordbox"


def test_preference_survives_settings_update_and_stays_out_of_settings():
    local_config.set_preference("build_target", "both")
    local_config.update_settings(showfile_url="https://www.showfile.events")
    assert local_config.get_preference("build_target", "serato") == "both"
    assert "build_target" not in local_config.get_settings()


def test_preference_rejects_unknown_key_and_value():
    with pytest.raises(ValueError):
        local_config.set_preference("build_target", "traktor")
    with pytest.raises(ValueError):
        local_config.get_preference("nope", "x")
