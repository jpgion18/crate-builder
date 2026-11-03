"""Resolve Serato's stored track paths to files on disk.

Serato stores paths relative to the root of the drive its `_Serato_` folder
lives on, without a leading slash:

* `~/Music/_Serato_` (system drive): `Users/joey/Music/a.mp3` means `/Users/joey/Music/a.mp3`
* `/Volumes/USB/_Serato_` (external): `Music/a.mp3` means `/Volumes/USB/Music/a.mp3`
* `C:\\Users\\joey\\Music\\_Serato_` (Windows): `Users/joey/Music/a.mp3` means `C:\\Users\\...`

Crate Builder's own crates store the full path with the leading slash
stripped (`Volumes/USB/Music/a.mp3`), and on Windows with the drive letter
(`C:/Users/joey/Music/a.mp3`); both resolve here too.

We try the drive root implied by the `_Serato_` location first, then the
system drive. Each candidate is also tried in NFC and NFD Unicode forms, since
macOS file names and Serato's stored strings don't always agree.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path, PurePath, PureWindowsPath

_DRIVE_LETTER = re.compile(r"^[A-Za-z]:/")


def drive_root_of(path: PurePath) -> PurePath:
    """The drive root of an absolute path, as the same kind of path.

    macOS: `/Volumes/<name>/...` maps to `/Volumes/<name>`, anything else to `/`.
    Windows: the drive, e.g. `C:\\`.
    """
    if isinstance(path, PureWindowsPath) or path.drive:
        return type(path)(path.anchor)
    parts = path.parts
    if len(parts) >= 3 and parts[0] == "/" and parts[1] == "Volumes":
        return type(path)(*parts[:3])
    return type(path)("/")


def drive_root_for(serato_dir: Path) -> Path:
    """The drive root a `_Serato_` folder's paths are relative to."""
    return Path(drive_root_of(serato_dir.resolve()))


def is_absolute_stored(stored: str) -> bool:
    """Whether a stored path (with `/` separators) is already absolute."""
    return stored.startswith("/") or bool(_DRIVE_LETTER.match(stored))


def candidate_paths(
    stored: str, serato_dir: Path, extra_roots: list[Path] | None = None
) -> list[Path]:
    stored = stored.replace("\\", "/")
    if is_absolute_stored(stored):
        bases = [Path(stored)]
    else:
        roots = [*(extra_roots or []), drive_root_for(serato_dir), serato_dir.resolve().parent]
        roots.append(Path(Path.home().anchor))  # the system drive: `/` or e.g. `C:\`
        bases = [root / stored for root in _unique(roots)]
    out: list[Path] = []
    for base in bases:
        for form in ("NFC", "NFD"):
            out.append(Path(unicodedata.normalize(form, str(base))))
    return _unique(out)


def resolve_track_path(
    stored: str, serato_dir: Path, extra_roots: list[Path] | None = None
) -> Path | None:
    for candidate in candidate_paths(stored, serato_dir, extra_roots):
        if candidate.is_file():
            return candidate
    return None


def _unique(items: list[Path]) -> list[Path]:
    seen: set[str] = set()
    out: list[Path] = []
    for item in items:
        key = str(item)
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out
