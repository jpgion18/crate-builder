import shutil
from pathlib import Path

import pytest

from crate_builder import metadata_editor

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def isolated_backups(tmp_path, monkeypatch):
    monkeypatch.setattr(metadata_editor, "_BACKUP_ROOT", str(tmp_path / "tag_backups"))


@pytest.fixture(params=["silence.mp3", "silence.flac"])
def audio_file(request, tmp_path):
    dest = tmp_path / request.param
    shutil.copy(FIXTURES / request.param, dest)
    return str(dest)


def test_read_tags_on_untagged_file_returns_empty_strings(audio_file):
    tags = metadata_editor.read_tags(audio_file)
    assert tags == {field: "" for field in metadata_editor.EDITABLE_FIELDS}


def test_write_then_read_round_trips(audio_file):
    metadata_editor.write_tags(audio_file, {"title": "New Title", "artist": "New Artist", "date": "2024"})
    tags = metadata_editor.read_tags(audio_file)
    assert tags["title"] == "New Title"
    assert tags["artist"] == "New Artist"
    assert tags["date"] == "2024"


def test_write_creates_a_backup_of_the_original(audio_file):
    original_bytes = Path(audio_file).read_bytes()

    backup_path = metadata_editor.write_tags(audio_file, {"title": "Changed"})

    assert Path(backup_path).exists()
    assert Path(backup_path).read_bytes() == original_bytes
    # The live file actually changed.
    assert metadata_editor.read_tags(audio_file)["title"] == "Changed"


def test_each_write_gets_its_own_backup(audio_file):
    backup_1 = metadata_editor.write_tags(audio_file, {"title": "First"})
    backup_2 = metadata_editor.write_tags(audio_file, {"title": "Second"})

    assert backup_1 != backup_2
    assert Path(backup_1).exists()
    assert Path(backup_2).exists()


def test_write_rejects_unknown_field(audio_file):
    with pytest.raises(metadata_editor.MetadataError):
        metadata_editor.write_tags(audio_file, {"bpm": "128"})


def test_write_missing_file_raises():
    with pytest.raises(metadata_editor.MetadataError):
        metadata_editor.write_tags("/no/such/file.mp3", {"title": "x"})


def test_restore_backup_reverts_the_file(audio_file):
    original_bytes = Path(audio_file).read_bytes()
    backup_path = metadata_editor.write_tags(audio_file, {"title": "Changed"})
    assert Path(audio_file).read_bytes() != original_bytes

    metadata_editor.restore_backup(backup_path)

    assert Path(audio_file).read_bytes() == original_bytes


def test_list_backups_reports_original_path_and_ordering(audio_file):
    metadata_editor.write_tags(audio_file, {"title": "First"})
    metadata_editor.write_tags(audio_file, {"title": "Second"})

    backups = metadata_editor.list_backups()

    assert len(backups) == 2
    assert all(b["original_path"] == audio_file for b in backups)
    # Newest first.
    assert backups[0]["backed_up_at"] >= backups[1]["backed_up_at"]


def test_list_backups_empty_when_nothing_backed_up():
    assert metadata_editor.list_backups() == []
