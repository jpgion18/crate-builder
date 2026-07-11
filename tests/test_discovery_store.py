from crate_builder import discovery_store


def _store_path(tmp_path):
    return str(tmp_path / "discovery_log.json")


def test_add_entries_and_list(tmp_path):
    path = _store_path(tmp_path)
    candidates = [
        {"artist": "Bicep", "title": "Glue", "raw": "Bicep - Glue"},
        {"artist": "Overmono", "title": "So U Kno", "raw": "Overmono - So U Kno"},
    ]
    result = discovery_store.add_entries(candidates, "Test Set", store_path=path)
    assert result["added_count"] == 2
    assert result["skipped_count"] == 0

    entries = discovery_store.list_entries(store_path=path)
    assert len(entries) == 2
    assert all(e["status"] == "new" for e in entries)
    assert all(e["source"] == "Test Set" for e in entries)


def test_add_entries_skips_duplicates(tmp_path):
    path = _store_path(tmp_path)
    candidates = [{"artist": "Bicep", "title": "Glue", "raw": "Bicep - Glue"}]
    discovery_store.add_entries(candidates, "First Set", store_path=path)

    # Same track, slightly different casing/punctuation, from a different source.
    dupes = [{"artist": "bicep", "title": "Glue!", "raw": "bicep - Glue!"}]
    result = discovery_store.add_entries(dupes, "Second Set", store_path=path)

    assert result["added_count"] == 0
    assert result["skipped_count"] == 1
    assert len(discovery_store.list_entries(store_path=path)) == 1


def test_update_status(tmp_path):
    path = _store_path(tmp_path)
    result = discovery_store.add_entries(
        [{"artist": "Bicep", "title": "Glue", "raw": "x"}], "src", store_path=path
    )
    entry_id = result["added"][0]["id"]

    assert discovery_store.update_status(entry_id, "acquired", store_path=path) is True
    entries = discovery_store.list_entries(store_path=path)
    assert entries[0]["status"] == "acquired"


def test_update_status_rejects_invalid_status(tmp_path):
    path = _store_path(tmp_path)
    result = discovery_store.add_entries(
        [{"artist": "Bicep", "title": "Glue", "raw": "x"}], "src", store_path=path
    )
    entry_id = result["added"][0]["id"]

    try:
        discovery_store.update_status(entry_id, "bogus", store_path=path)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_update_status_unknown_id_returns_false(tmp_path):
    path = _store_path(tmp_path)
    assert discovery_store.update_status("nonexistent", "acquired", store_path=path) is False


def test_delete_entry(tmp_path):
    path = _store_path(tmp_path)
    result = discovery_store.add_entries(
        [{"artist": "Bicep", "title": "Glue", "raw": "x"}], "src", store_path=path
    )
    entry_id = result["added"][0]["id"]

    assert discovery_store.delete_entry(entry_id, store_path=path) is True
    assert discovery_store.list_entries(store_path=path) == []
    assert discovery_store.delete_entry(entry_id, store_path=path) is False


def test_build_discovery_log_csv():
    entries = [
        {
            "artist": "Bicep",
            "title": "Glue",
            "source": "Test Set",
            "date_added": "2026-07-11T00:00:00+00:00",
            "status": "new",
        }
    ]
    csv_text = discovery_store.build_discovery_log_csv(entries)
    lines = csv_text.strip().splitlines()
    assert lines[0] == "Artist,Title,Source,Date Added,Status"
    assert lines[1] == "Bicep,Glue,Test Set,2026-07-11T00:00:00+00:00,new"


def test_list_entries_empty_when_no_file(tmp_path):
    path = _store_path(tmp_path)
    assert discovery_store.list_entries(store_path=path) == []
