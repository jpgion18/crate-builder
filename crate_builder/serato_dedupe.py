"""Remove duplicate tracks from a Serato library, safely.

This is the only part of crate-builder that edits Serato's own library
(the "database V2" file and the .crate files in Subcrates), so it is built
around three guarantees:

1. **Nothing happens without a backup.** Before any write, the database
   and every crate file are copied into a timestamped folder under
   ~/.crate_builder/serato_backups/. Every run can be undone from there.
2. **Crates keep their songs.** A removed copy's spot in each crate is
   handed to the copy you chose to keep (or simply dropped, when the kept
   copy is already in that crate), so no crate loses a track.
3. **Files are never deleted outright.** A removed copy's audio file is
   either left where it is, or moved into a "Removed Duplicates" folder in
   your home folder (same sub-path as before), where you can check it and
   empty it yourself. Undo moves it back.

Everything that isn't a removed track is written back byte-for-byte, so
cue points, beatgrids, play counts and fields this code doesn't know about
are untouched.

Serato keeps its library in memory and writes it back on quit, so it must
be closed while this runs, or it will simply overwrite the cleanup.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime

from crate_builder import serato_paths
from crate_builder.duplicates import find_duplicates
from crate_builder.serato_database import SeratoDatabaseError, parse_database, resolve_serato_path
from crate_builder.seratobox.serato.tlv import TLVError, decode_str, encode_record, encode_str, iter_records

_BACKUP_ROOT = os.path.join(os.path.expanduser("~"), ".crate_builder", "serato_backups")
_REMOVED_ROOT = os.path.join(os.path.expanduser("~"), "Crate Builder Removed Duplicates")

FILE_ACTIONS = ("move", "keep")


class DedupeError(RuntimeError):
    pass


@dataclass
class RemovalPlan:
    """One duplicate group's decision: keep `keep`, remove everything in `remove`."""

    keep: str
    remove: list[str]


@dataclass
class DedupeResult:
    backup_id: str
    removed_from_database: int
    crates_updated: list[str] = field(default_factory=list)
    files_moved: list[dict] = field(default_factory=list)
    file_errors: list[str] = field(default_factory=list)


def _key(path: str) -> str:
    return os.path.normcase(os.path.normpath(path)) if path else ""


# ---- Serato running check ----


def serato_is_running() -> bool:
    """Best-effort: True only when we can positively see Serato DJ running."""
    try:
        if serato_paths.is_windows():
            out = subprocess.run(["tasklist"], capture_output=True, text=True, timeout=5).stdout
        else:
            out = subprocess.run(["ps", "-axo", "comm"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    lowered = out.lower()
    return "serato dj" in lowered or "serato_dj" in lowered


# ---- Backups ----


def _crate_files(serato_dir: str) -> list[str]:
    subcrates = serato_paths.subcrates_dir(serato_dir)
    if not os.path.isdir(subcrates):
        return []
    return sorted(
        os.path.join(subcrates, name)
        for name in os.listdir(subcrates)
        if name.endswith(".crate") and os.path.isfile(os.path.join(subcrates, name))
    )


def backup_serato(serato_dir: str) -> str:
    """Copy database V2 and every .crate into a new backup folder. Returns its id."""
    db_path = serato_paths.database_v2_path(serato_dir)
    if not os.path.isfile(db_path):
        raise DedupeError(f"Serato database not found: {db_path}")

    backup_id = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup_dir = os.path.join(_BACKUP_ROOT, backup_id)
    os.makedirs(os.path.join(backup_dir, "Subcrates"), exist_ok=True)
    shutil.copy2(db_path, os.path.join(backup_dir, "database V2"))
    crates = _crate_files(serato_dir)
    for crate in crates:
        shutil.copy2(crate, os.path.join(backup_dir, "Subcrates", os.path.basename(crate)))

    _write_manifest(
        backup_dir,
        {
            "serato_dir": os.path.abspath(serato_dir),
            "created_at": backup_id,
            "crates": [os.path.basename(c) for c in crates],
            "removed_tracks": [],
            "moved_files": [],
            "restored": False,
        },
    )
    return backup_id


def _write_manifest(backup_dir: str, manifest: dict) -> None:
    with open(os.path.join(backup_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)


def _read_manifest(backup_id: str) -> tuple[str, dict]:
    if not backup_id or os.sep in backup_id or "/" in backup_id or backup_id.startswith("."):
        raise DedupeError("Invalid backup id")
    backup_dir = os.path.join(_BACKUP_ROOT, backup_id)
    manifest_path = os.path.join(backup_dir, "manifest.json")
    if not os.path.isfile(manifest_path):
        raise DedupeError(f"Backup not found: {backup_id}")
    with open(manifest_path) as f:
        return backup_dir, json.load(f)


def list_serato_backups() -> list[dict]:
    if not os.path.isdir(_BACKUP_ROOT):
        return []
    results = []
    for backup_id in os.listdir(_BACKUP_ROOT):
        try:
            _, manifest = _read_manifest(backup_id)
        except (DedupeError, OSError, ValueError):
            continue
        results.append(
            {
                "backup_id": backup_id,
                "serato_dir": manifest.get("serato_dir", ""),
                "removed_count": len(manifest.get("removed_tracks", [])),
                "moved_count": len(manifest.get("moved_files", [])),
                "restored": bool(manifest.get("restored")),
            }
        )
    results.sort(key=lambda r: r["backup_id"], reverse=True)
    return results


def restore_serato_backup(backup_id: str) -> dict:
    """Put the database and crates back exactly as they were, and move any
    quarantined files back to where they came from."""
    backup_dir, manifest = _read_manifest(backup_id)
    serato_dir = manifest["serato_dir"]
    if serato_is_running():
        raise DedupeError("Quit Serato DJ before restoring — it would overwrite the restored library when it closes.")

    file_errors: list[str] = []
    for moved in manifest.get("moved_files", []):
        src, dest = moved["moved_to"], moved["original_path"]
        if os.path.exists(dest):
            continue  # already back (or something new is there); never overwrite
        if not os.path.exists(src):
            file_errors.append(f"Missing from the Removed Duplicates folder: {src}")
            continue
        try:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.move(src, dest)
        except OSError as exc:
            file_errors.append(f"Couldn't move {src} back: {exc}")

    _atomic_copy(os.path.join(backup_dir, "database V2"), serato_paths.database_v2_path(serato_dir))
    subcrates = serato_paths.subcrates_dir(serato_dir)
    for name in manifest.get("crates", []):
        _atomic_copy(os.path.join(backup_dir, "Subcrates", name), os.path.join(subcrates, name))

    manifest["restored"] = True
    _write_manifest(backup_dir, manifest)
    return {"serato_dir": serato_dir, "file_errors": file_errors}


# ---- Writing ----


def _atomic_write(dest: str, data: bytes) -> None:
    directory = os.path.dirname(dest) or "."
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".crate_builder_tmp_")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        if os.path.exists(dest):
            shutil.copymode(dest, tmp)
        os.replace(tmp, dest)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def _atomic_copy(src: str, dest: str) -> None:
    with open(src, "rb") as f:
        _atomic_write(dest, f.read())


def _track_pfil(payload: bytes) -> str:
    for tag, value in iter_records(payload):
        if tag == "pfil":
            return decode_str(value)
    return ""


def rewrite_database(data: bytes, remove_keys: set[str]) -> tuple[bytes, int]:
    """Drop every top-level otrk whose path is in remove_keys; everything
    else is copied through unchanged. Returns (new bytes, tracks dropped)."""
    out = bytearray()
    dropped = 0
    for tag, value in iter_records(data):
        if tag == "otrk" and _key(resolve_serato_path(_track_pfil(value))) in remove_keys:
            dropped += 1
            continue
        out += encode_record(tag, value)
    return bytes(out), dropped


def rewrite_crate(data: bytes, replacements: dict[str, str]) -> tuple[bytes, bool]:
    """Point crate entries for removed copies at the kept copy (raw Serato
    path), dropping the entry when the kept copy is already in the crate.
    Returns (new bytes, changed)."""
    records = list(iter_records(data))
    present = set()
    for tag, value in records:
        if tag == "otrk":
            present.add(_key(resolve_serato_path(_ptrk(value))))

    out = bytearray()
    changed = False
    for tag, value in records:
        if tag != "otrk":
            out += encode_record(tag, value)
            continue
        key = _key(resolve_serato_path(_ptrk(value)))
        if key not in replacements:
            out += encode_record(tag, value)
            continue
        changed = True
        keep_raw = replacements[key]
        keep_key = _key(resolve_serato_path(keep_raw))
        if keep_key in present:
            continue
        present.add(keep_key)
        out += encode_record("otrk", _replace_ptrk(value, keep_raw))
    return bytes(out), changed


def _ptrk(otrk_value: bytes) -> str:
    for tag, value in iter_records(otrk_value):
        if tag == "ptrk":
            return decode_str(value)
    return ""


def _replace_ptrk(otrk_value: bytes, new_path: str) -> bytes:
    out = bytearray()
    for tag, value in iter_records(otrk_value):
        out += encode_record(tag, encode_str(new_path) if tag == "ptrk" else value)
    return bytes(out)


def _quarantine_path(original: str, run_id: str) -> str:
    drive, rest = os.path.splitdrive(os.path.abspath(original))
    rest = rest.lstrip("\\/")
    parts = [_REMOVED_ROOT, run_id]
    if drive:
        parts.append(drive.replace(":", "").strip("\\/") or "drive")
    return os.path.join(*parts, rest)


def _validate_plans(serato_dir: str, plans: list[RemovalPlan]) -> tuple[dict[str, str], dict[str, str]]:
    """Check every plan against the duplicate groups found in the current
    database: the kept copy and every removed copy must be in the same
    group, a track can't be both kept and removed, and at least one copy of
    every group survives. Returns (remove key -> kept raw Serato path,
    remove key -> resolved path of the removed copy)."""
    db_path = serato_paths.database_v2_path(serato_dir)
    try:
        tracks = parse_database(db_path)
    except SeratoDatabaseError as exc:
        raise DedupeError(str(exc)) from exc

    group_of: dict[str, int] = {}
    for i, group in enumerate(find_duplicates(tracks)):
        for t in group.tracks:
            group_of[_key(t.path)] = i

    raw_by_key = _raw_paths(db_path)
    keep_keys: set[str] = set()
    replacements: dict[str, str] = {}
    resolved: dict[str, str] = {}
    for plan in plans:
        keep_key = _key(plan.keep)
        if keep_key not in group_of:
            raise DedupeError(f"Not a duplicate in your current Serato library: {plan.keep} — scan again.")
        if not plan.remove:
            continue
        for path in plan.remove:
            key = _key(path)
            if key == keep_key:
                raise DedupeError(f"Can't keep and remove the same track: {path}")
            if group_of.get(key) != group_of[keep_key]:
                raise DedupeError(f"{path} isn't in the same duplicate group as {plan.keep} — scan again.")
            replacements[key] = raw_by_key[keep_key]
            resolved[key] = path
        keep_keys.add(keep_key)

    clash = keep_keys & set(replacements)
    if clash:
        raise DedupeError("A track is marked both keep and remove: " + ", ".join(sorted(clash)))
    return replacements, resolved


def _raw_paths(db_path: str) -> dict[str, str]:
    with open(db_path, "rb") as f:
        data = f.read()
    result = {}
    for tag, value in iter_records(data):
        if tag == "otrk":
            raw = _track_pfil(value)
            if raw:
                result[_key(resolve_serato_path(raw))] = raw
    return result


def remove_duplicates(serato_dir: str, plans: list[RemovalPlan], file_action: str = "move") -> DedupeResult:
    if file_action not in FILE_ACTIONS:
        raise DedupeError(f"file_action must be one of {', '.join(FILE_ACTIONS)}")
    serato_dir = os.path.abspath(os.path.expanduser(serato_dir))
    if serato_is_running():
        raise DedupeError("Quit Serato DJ first — it rewrites its library when it closes and would undo this cleanup.")

    try:
        replacements, resolved = _validate_plans(serato_dir, plans)
    except (TLVError, KeyError) as exc:
        raise DedupeError(f"Couldn't read the Serato database: {exc}") from exc
    if not replacements:
        raise DedupeError("Nothing selected to remove.")

    # Parse everything before writing anything, so a bad crate file stops
    # the run before the library is half-edited.
    db_path = serato_paths.database_v2_path(serato_dir)
    with open(db_path, "rb") as f:
        new_db, dropped = rewrite_database(f.read(), set(replacements))
    crate_writes: list[tuple[str, bytes]] = []
    for crate_path in _crate_files(serato_dir):
        with open(crate_path, "rb") as f:
            try:
                new_crate, changed = rewrite_crate(f.read(), replacements)
            except TLVError as exc:
                raise DedupeError(f"Couldn't read crate {os.path.basename(crate_path)}: {exc}") from exc
        if changed:
            crate_writes.append((crate_path, new_crate))

    backup_id = backup_serato(serato_dir)
    backup_dir, manifest = _read_manifest(backup_id)
    manifest["removed_tracks"] = sorted(resolved.values())

    _atomic_write(db_path, new_db)
    for crate_path, new_crate in crate_writes:
        _atomic_write(crate_path, new_crate)

    result = DedupeResult(
        backup_id=backup_id,
        removed_from_database=dropped,
        crates_updated=[os.path.basename(p)[: -len(".crate")].replace("%%", " > ") for p, _ in crate_writes],
    )

    if file_action == "move":
        for path in sorted(resolved.values()):
            if not os.path.isfile(path):
                result.file_errors.append(f"File already gone: {path}")
                continue
            dest = _quarantine_path(path, backup_id)
            try:
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                shutil.move(path, dest)
            except OSError as exc:
                result.file_errors.append(f"Couldn't move {path}: {exc}")
                continue
            entry = {"original_path": path, "moved_to": dest}
            result.files_moved.append(entry)
            manifest["moved_files"].append(entry)
            _write_manifest(backup_dir, manifest)  # after each move, so undo knows even if we crash

    _write_manifest(backup_dir, manifest)
    return result


def removed_duplicates_folder() -> str:
    return _REMOVED_ROOT


def suggest_keep(tracks: list[dict]) -> str:
    """Pick the copy to keep by default: one whose file still exists, then
    the one in the most crates, then the biggest file (usually the higher
    quality rip)."""
    def score(t: dict):
        return (bool(t.get("exists")), t.get("crate_count", 0), t.get("file_size") or 0)

    return max(tracks, key=score)["path"] if tracks else ""


def crate_counts(serato_dir: str) -> dict[str, int]:
    """normcase'd path -> number of crates it's in."""
    counts: dict[str, int] = {}
    for crate_path in _crate_files(serato_dir):
        try:
            with open(crate_path, "rb") as f:
                data = f.read()
            seen = set()
            for tag, value in iter_records(data):
                if tag == "otrk":
                    seen.add(_key(resolve_serato_path(_ptrk(value))))
        except (OSError, TLVError):
            continue
        for key in seen:
            counts[key] = counts.get(key, 0) + 1
    return counts


__all__ = [
    "DedupeError",
    "DedupeResult",
    "FILE_ACTIONS",
    "RemovalPlan",
    "backup_serato",
    "crate_counts",
    "list_serato_backups",
    "remove_duplicates",
    "removed_duplicates_folder",
    "restore_serato_backup",
    "rewrite_crate",
    "rewrite_database",
    "serato_is_running",
    "suggest_keep",
]
