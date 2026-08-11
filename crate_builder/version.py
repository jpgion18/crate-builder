"""Reads the app's version from a VERSION file at the repo root (or, once
packaged, the PyInstaller bundle root).

The committed VERSION file just says "dev" — that's what you see running
from source or from a manual PyInstaller build. Real version numbers are
baked in by .github/workflows/build-desktop.yml, which overwrites VERSION
with the actual git tag (e.g. "v0.6.1") right before packaging a tagged
release, so the number shown always matches what was actually built rather
than something hand-maintained in source that could drift from the tag.
"""

from __future__ import annotations

import os


def get_version(base_dir: str) -> str:
    try:
        with open(os.path.join(base_dir, "VERSION")) as f:
            return f.read().strip() or "dev"
    except FileNotFoundError:
        return "dev"
