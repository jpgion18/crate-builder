"""Helpers for locating the Serato database and turning a name into a safe .crate path."""

from __future__ import annotations

import os
import re
import sys

_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*]')


def guess_music_dir() -> str:
    """Best-effort default for where a user's music library usually lives."""
    home = os.path.expanduser("~")
    return os.path.join(home, "Music")


def guess_serato_dir() -> str:
    """Best-effort default for the _Serato_ folder Serato DJ creates.

    Serato normally creates this inside whichever folder you pointed it at
    during setup (commonly the Music folder). If yours lives somewhere else,
    just override the path in the UI.
    """
    return os.path.join(guess_music_dir(), "_Serato_")


def subcrates_dir(serato_dir: str) -> str:
    return os.path.join(serato_dir, "Subcrates")


def sanitize_crate_name(name: str) -> str:
    """Turn a user-supplied crate name into a safe .crate filename.

    Serato represents nested crates ("Parent > Child") with a '%%' separator
    in the filename, so we preserve '>' as a hierarchy hint before stripping
    other unsafe characters.
    """
    name = name.strip()
    if not name:
        raise ValueError("Crate name cannot be empty")

    parts = [p.strip() for p in name.split(">") if p.strip()]
    parts = [_INVALID_FILENAME_CHARS.sub("_", p) for p in parts]
    filename = "%%".join(parts) if parts else "New Crate"
    if not filename.lower().endswith(".crate"):
        filename += ".crate"
    return filename


def is_windows() -> bool:
    return sys.platform.startswith("win")
