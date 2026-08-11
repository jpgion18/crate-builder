"""Read and write ID3/tag metadata on local audio files.

This is the first part of crate-builder that modifies files in your actual
music library, rather than only reading them (like scanning) or writing
new files elsewhere (like a Serato crate) — so every write backs up the
original file first, unconditionally, before touching it. Backups are kept
per-edit (not just the very first one) so you can step back through a
history of changes, not just revert all the way to the original.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime

from mutagen import File as MutagenFile

_BACKUP_ROOT = os.path.join(os.path.expanduser("~"), ".crate_builder", "tag_backups")

# mutagen's "easy" key names, consistent across MP3/MP4/FLAC/Ogg.
EDITABLE_FIELDS = ("title", "artist", "album", "genre", "date", "tracknumber")


class MetadataError(RuntimeError):
    pass


def read_tags(path: str) -> dict[str, str]:
    if not os.path.isfile(path):
        raise MetadataError(f"File not found: {path}")
    try:
        audio = MutagenFile(path, easy=True)
    except Exception as exc:
        raise MetadataError(f"Couldn't read tags: {exc}") from exc
    if audio is None:
        raise MetadataError(f"Unsupported audio format: {path}")
    tags = audio.tags or {}
    return {field: (tags.get(field) or [""])[0] for field in EDITABLE_FIELDS}


def _backup_dir_for(path: str) -> str:
    digest = hashlib.sha256(os.path.abspath(path).encode()).hexdigest()[:16]
    return os.path.join(_BACKUP_ROOT, digest)


def _backup_file(path: str) -> str:
    backup_dir = _backup_dir_for(path)
    os.makedirs(backup_dir, exist_ok=True)

    manifest_path = os.path.join(backup_dir, "manifest.json")
    if not os.path.exists(manifest_path):
        with open(manifest_path, "w") as f:
            json.dump({"original_path": os.path.abspath(path)}, f)

    # Microsecond precision so two edits saved in quick succession — very
    # plausible from a UI where each field tweak is its own save — don't
    # land on the same filename and silently clobber an earlier backup.
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup_path = os.path.join(backup_dir, f"{timestamp}_{os.path.basename(path)}")
    shutil.copy2(path, backup_path)
    return backup_path


def write_tags(path: str, fields: dict[str, str]) -> str:
    """Backs up path, then writes the given fields (a subset of
    EDITABLE_FIELDS) to it. Returns the backup path."""
    if not os.path.isfile(path):
        raise MetadataError(f"File not found: {path}")
    unknown = set(fields) - set(EDITABLE_FIELDS)
    if unknown:
        raise MetadataError(f"Unsupported field(s): {', '.join(sorted(unknown))}")

    backup_path = _backup_file(path)

    try:
        audio = MutagenFile(path, easy=True)
        if audio is None:
            raise MetadataError(f"Unsupported audio format: {path}")
        if audio.tags is None:
            audio.add_tags()
        for field, value in fields.items():
            value = (value or "").strip()
            if value:
                audio.tags[field] = [value]
            elif field in audio.tags:
                del audio.tags[field]
        audio.save()
    except MetadataError:
        raise
    except Exception as exc:
        raise MetadataError(f"Couldn't write tags ({exc}) — original backed up at {backup_path}") from exc

    return backup_path


def list_backups() -> list[dict]:
    """All known backups, newest first."""
    if not os.path.isdir(_BACKUP_ROOT):
        return []

    results: list[dict] = []
    for digest in os.listdir(_BACKUP_ROOT):
        entry_dir = os.path.join(_BACKUP_ROOT, digest)
        manifest_path = os.path.join(entry_dir, "manifest.json")
        if not os.path.isfile(manifest_path):
            continue
        with open(manifest_path) as f:
            manifest = json.load(f)
        for filename in os.listdir(entry_dir):
            if filename == "manifest.json":
                continue
            results.append(
                {
                    "original_path": manifest["original_path"],
                    "backup_path": os.path.join(entry_dir, filename),
                    "backed_up_at": filename.split("_", 1)[0],
                }
            )

    results.sort(key=lambda r: r["backed_up_at"], reverse=True)
    return results


def restore_backup(backup_path: str) -> None:
    if not os.path.isfile(backup_path):
        raise MetadataError(f"Backup not found: {backup_path}")
    manifest_path = os.path.join(os.path.dirname(backup_path), "manifest.json")
    if not os.path.isfile(manifest_path):
        raise MetadataError("Missing backup manifest — can't determine the original file's path.")
    with open(manifest_path) as f:
        manifest = json.load(f)
    shutil.copy2(backup_path, manifest["original_path"])
