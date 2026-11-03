"""Command-line wrapper around `seratobox.convert`. Parses arguments, prints the report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .core import ConvertError, convert
from .options import ConvertOptions, CueMode

DEFAULT_SERATO_DIR = Path("~/Music/_Serato_")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m crate_builder.seratobox",
        description="Convert Serato DJ Pro crates to a Rekordbox XML file (read-only on Serato).",
    )
    p.add_argument(
        "sources",
        nargs="*",
        help="crate names (House, 'House%%%%Deep' or House/Deep) and/or audio file paths",
    )
    p.add_argument("-o", "--output", type=Path, help="Rekordbox XML file to write")
    p.add_argument(
        "--serato-dir",
        type=Path,
        default=DEFAULT_SERATO_DIR,
        help=f"the _Serato_ folder (default: {DEFAULT_SERATO_DIR})",
    )
    p.add_argument("--all", action="store_true", help="convert every crate")
    p.add_argument(
        "--cue-mode",
        choices=[m.value for m in CueMode],
        default=CueMode.BOTH.value,
        help="hotcues, memory, or both (default: both)",
    )
    p.add_argument(
        "--mp3-offset",
        default="auto",
        help="MP3 cue shift: auto, off, or milliseconds, e.g. 26 (default: auto)",
    )
    p.add_argument(
        "--no-subcrates",
        action="store_true",
        help="skip crates nested under the selected ones",
    )
    p.add_argument(
        "--path-root",
        action="append",
        type=Path,
        default=[],
        help="extra drive root to resolve Serato track paths against (repeatable)",
    )
    p.add_argument("-n", "--dry-run", action="store_true", help="parse and report; write nothing")
    p.add_argument("--json", action="store_true", help="print the report as JSON")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.dry_run and args.output is None:
        print("error: --output is required unless --dry-run is given", file=sys.stderr)
        return 2
    options = ConvertOptions(
        cue_mode=CueMode(args.cue_mode),
        dry_run=args.dry_run,
        mp3_offset=args.mp3_offset,
        include_subcrates=not args.no_subcrates,
        all_crates=args.all,
        path_roots=args.path_root,
    )
    try:
        options.mp3_offset_mode()
        report = convert(args.sources, args.serato_dir, args.output, options)
    except (ConvertError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report.to_dict(), indent=2) if args.json else report.render())
    return 0


if __name__ == "__main__":
    sys.exit(main())
