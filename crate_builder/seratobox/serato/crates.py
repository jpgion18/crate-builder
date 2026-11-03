"""Read Serato `.crate` files from `_Serato_/Subcrates`.

Nesting is encoded in the file name: `House%%Deep%%Late.crate` is the crate
`Late` inside `Deep` inside `House`. Each track is an `otrk` record holding a
`ptrk` path relative to the drive root.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .models import Crate
from .tlv import TLVError, decode_str, iter_records

SEPARATOR = "%%"
SUBCRATES_DIR = "Subcrates"


def parse_crate_bytes(data: bytes) -> list[str]:
    paths: list[str] = []
    for tag, value in iter_records(data):
        if tag != "otrk":
            continue
        for sub_tag, sub_value in iter_records(value):
            if sub_tag == "ptrk":
                paths.append(decode_str(sub_value))
    return paths


def crate_parts_from_filename(filename: str) -> tuple[str, ...]:
    stem = filename[: -len(".crate")] if filename.endswith(".crate") else filename
    return tuple(stem.split(SEPARATOR))


def read_crate(path: Path) -> Crate:
    return Crate(
        parts=crate_parts_from_filename(path.name),
        track_paths=parse_crate_bytes(path.read_bytes()),
        file=path,
    )


def list_crate_files(serato_dir: Path) -> list[Path]:
    subcrates = serato_dir / SUBCRATES_DIR
    if not subcrates.is_dir():
        return []
    return sorted(p for p in subcrates.iterdir() if p.suffix == ".crate" and p.is_file())


def read_all_crates(serato_dir: Path, warnings: list[str] | None = None) -> list[Crate]:
    crates: list[Crate] = []
    for path in list_crate_files(serato_dir):
        try:
            crates.append(read_crate(path))
        except (OSError, TLVError) as exc:
            if warnings is None:
                raise
            warnings.append(f"Skipped unreadable crate {path.name}: {exc}")
    return crates


def parse_crate_name(name: str) -> tuple[str, ...]:
    """Accept `House%%Deep`, `House/Deep` or `House > Deep` as a crate reference."""
    for sep in (SEPARATOR, " > ", "/"):
        if sep in name:
            return tuple(part.strip() for part in name.split(sep))
    return (name.strip(),)


def select_crates(
    crates: list[Crate], names: list[str], include_subcrates: bool = True
) -> tuple[list[Crate], list[str]]:
    """Return the crates matching `names` (plus their subcrates) and the names not found.

    Matching is exact first, then case-insensitive.
    """
    selected: dict[tuple[str, ...], Crate] = {}
    missing: list[str] = []
    for name in names:
        wanted = parse_crate_name(name)
        matches = [c for c in crates if _is_under(c.parts, wanted, include_subcrates)]
        if not matches:
            lowered = tuple(p.lower() for p in wanted)
            matches = [
                c
                for c in crates
                if _is_under(tuple(p.lower() for p in c.parts), lowered, include_subcrates)
            ]
        if not matches:
            missing.append(name)
        for crate in matches:
            selected.setdefault(crate.parts, crate)
    return sorted(selected.values(), key=lambda c: c.parts), missing


def _is_under(parts: tuple[str, ...], prefix: tuple[str, ...], include_children: bool) -> bool:
    if include_children:
        return parts[: len(prefix)] == prefix
    return parts == prefix


@dataclass
class CrateNode:
    """One crate in the nested crate tree. `crate` is None for a parent with no .crate file."""

    name: str
    parts: tuple[str, ...]
    crate: Crate | None = None
    children: list[CrateNode] = field(default_factory=list)

    @property
    def ref(self) -> str:
        """The name to pass to `convert()` for exactly this crate."""
        return SEPARATOR.join(self.parts)

    @property
    def track_count(self) -> int:
        return len(self.crate.track_paths) if self.crate else 0


def crate_tree(crates: list[Crate]) -> list[CrateNode]:
    """Nest crates by their `%%` path, sorted case-insensitively at each level."""
    roots: list[CrateNode] = []
    index: dict[tuple[str, ...], CrateNode] = {}
    for crate in sorted(crates, key=lambda c: tuple(p.lower() for p in c.parts)):
        siblings = roots
        for depth in range(1, len(crate.parts) + 1):
            parts = crate.parts[:depth]
            node = index.get(parts)
            if node is None:
                node = index[parts] = CrateNode(name=parts[-1], parts=parts)
                siblings.append(node)
            siblings = node.children
        index[crate.parts].crate = crate
    return roots
