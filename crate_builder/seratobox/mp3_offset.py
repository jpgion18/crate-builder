"""MP3 cue offset policy.

Serato and Rekordbox use different MP3 decoders. Depending on how a file was
encoded (whether its first frame is a Xing/Info header, whether a LAME tag
records the encoder delay), the two can disagree about where sample 0 is, which
shifts every cue, loop and grid marker by a constant amount (typically about one
MPEG frame, roughly 26 ms at 44.1 kHz).

`auto` classifies each MP3 so the report shows which files are at risk. The
shift it applies per class lives in AUTO_SHIFT_MS and is 0 until calibrated
against real tracks checked in both applications. Use a fixed `--mp3-offset <ms>`
to apply a known shift to every MP3 in the meantime.
"""

from __future__ import annotations

from .serato.models import Mp3Framing

# Milliseconds added to Serato positions per framing class, pending calibration.
AUTO_SHIFT_MS: dict[str, float] = {
    "lame": 0.0,  # Xing/Info frame with a LAME tag (gapless info present)
    "xing_no_lame": 0.0,  # Xing/Info frame without a LAME tag
    "no_xing": 0.0,  # no header frame (typical of some older or non-LAME encoders)
}


def classify(framing: Mp3Framing | None) -> str:
    if framing is None or not framing.has_xing:
        return "no_xing"
    return "lame" if framing.has_lame else "xing_no_lame"


def describe(framing: Mp3Framing | None) -> str:
    if framing is None:
        return "framing unknown"
    if not framing.has_xing:
        return "no Xing/Info header"
    if not framing.has_lame:
        return "Xing/Info header, no LAME tag"
    return f"LAME tag, encoder delay {framing.encoder_delay}, padding {framing.padding} samples"


def offset_ms(mode: str, fixed_ms: float, framing: Mp3Framing | None) -> float:
    if mode == "off":
        return 0.0
    if mode == "fixed":
        return fixed_ms
    return AUTO_SHIFT_MS[classify(framing)]
