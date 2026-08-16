import pytest

from crate_builder import discover_sources


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr(discover_sources, "STORE_PATH", str(tmp_path / "discover_sources.json"))


def test_empty_by_default():
    assert discover_sources.list_sources() == []


def test_add_and_list():
    entry = discover_sources.add_source("DJCity Weekly Pool", "https://www.djcity.com", "Pool", "General")
    assert entry["name"] == "DJCity Weekly Pool"
    assert entry["category"] == "General"
    assert "id" in entry

    sources = discover_sources.list_sources()
    assert len(sources) == 1
    assert sources[0]["id"] == entry["id"]


def test_add_requires_a_name():
    with pytest.raises(ValueError):
        discover_sources.add_source("", "", "Pool", "General")


def test_add_rejects_unknown_type():
    with pytest.raises(ValueError):
        discover_sources.add_source("Name", "", "NotAType", "General")


def test_add_rejects_unknown_category():
    with pytest.raises(ValueError):
        discover_sources.add_source("Name", "", "Pool", "NotACategory")


def test_remove_source():
    entry = discover_sources.add_source("Name", "", "Pool", "General")
    assert discover_sources.remove_source(entry["id"]) is True
    assert discover_sources.list_sources() == []


def test_remove_unknown_id_returns_false():
    assert discover_sources.remove_source("no-such-id") is False


def test_sources_in_different_categories_stay_independent():
    discover_sources.add_source("Wedding Playlist", "", "Spotify", "Wedding")
    discover_sources.add_source("Club Chart", "", "Tracklist", "Club Open")
    sources = discover_sources.list_sources()
    categories = {s["category"] for s in sources}
    assert categories == {"Wedding", "Club Open"}
