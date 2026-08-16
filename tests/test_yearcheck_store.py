import pytest

from crate_builder import yearcheck_store


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr(yearcheck_store, "STORE_PATH", str(tmp_path / "year_check_results.json"))


def test_empty_by_default():
    assert yearcheck_store.get_cached_results() == []
    assert not yearcheck_store.is_checked("Artist", "Title")


def test_save_and_retrieve():
    yearcheck_store.save_result("Artist A", "Song One", {"status": "match", "mb_year": "2019"})
    assert yearcheck_store.is_checked("Artist A", "Song One")
    results = yearcheck_store.get_cached_results()
    assert len(results) == 1
    assert results[0]["mb_year"] == "2019"


def test_key_is_case_and_whitespace_insensitive():
    yearcheck_store.save_result("Artist A", "Song One", {"status": "match"})
    assert yearcheck_store.is_checked("  artist a  ", "SONG ONE")


def test_saving_same_track_again_overwrites_not_duplicates():
    yearcheck_store.save_result("Artist A", "Song One", {"status": "notfound"})
    yearcheck_store.save_result("Artist A", "Song One", {"status": "match", "mb_year": "2019"})
    results = yearcheck_store.get_cached_results()
    assert len(results) == 1
    assert results[0]["status"] == "match"


def test_clear_cache():
    yearcheck_store.save_result("Artist A", "Song One", {"status": "match"})
    yearcheck_store.clear_cache()
    assert yearcheck_store.get_cached_results() == []
    assert not yearcheck_store.is_checked("Artist A", "Song One")
