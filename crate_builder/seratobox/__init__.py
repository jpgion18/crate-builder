"""SeratoBox: read-only Serato DJ Pro to Rekordbox XML converter.

Powers Crate Builder's Rekordbox tab. Originally the standalone SeratoBox app
(github.com/jpgion18/SeratoBox); has no dependency on the rest of Crate Builder.

from crate_builder.seratobox import convert, ConvertOptions, CueMode
report = convert(["House"], "~/Music/_Serato_", "out.xml", ConvertOptions())
print(report.render())
"""

__version__ = "0.3.0"

from .core import ConvertError, convert, export_playlist  # noqa: E402
from .options import ConvertOptions, CueMode  # noqa: E402
from .report import Report, TrackReport  # noqa: E402

__all__ = [
    "ConvertError",
    "ConvertOptions",
    "CueMode",
    "Report",
    "TrackReport",
    "__version__",
    "convert",
    "export_playlist",
]
