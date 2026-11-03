"""Markers2 and BeatGrid payload decoding, independent of file format."""

from __future__ import annotations

import base64

import pytest
from seratobox_fixtures import FCue, FLoop, FTrack, beatgrid_bytes, markers2_payload, wrap_markers2

from crate_builder.seratobox.serato.beatgrid import BeatGridError, decode_beatgrid, segment_bpm
from crate_builder.seratobox.serato.markers2 import (
    MarkersError,
    decode_markers2,
    lenient_b64decode,
    parse_markers2_payload,
)
from crate_builder.seratobox.serato.models import Color


def test_markers2_round_trip() -> None:
    track = FTrack(
        cues=[FCue(5, 999_999, (0x00, 0x88, 0xCC), "Späť ✓"), FCue(0, 0)],
        loops=[FLoop(3, 1500, 3500, (1, 2, 3), "Loop", locked=True)],
        track_color=(0x99, 0xFF, 0x99),
    )
    markers, warnings = decode_markers2(wrap_markers2(markers2_payload(track)))
    assert warnings == []
    assert [(c.index, c.position_ms, c.name) for c in markers.cues] == [
        (0, 0, ""),
        (5, 999_999, "Späť ✓"),
    ]
    assert markers.cues[1].color == Color(0x00, 0x88, 0xCC)
    (loop,) = markers.loops
    assert (loop.index, loop.start_ms, loop.end_ms, loop.name, loop.locked) == (
        3,
        1500,
        3500,
        "Loop",
        True,
    )
    assert loop.color == Color(1, 2, 3)
    assert markers.track_color == Color(0x99, 0xFF, 0x99)


def test_unknown_entries_are_skipped() -> None:
    payload = markers2_payload(FTrack(cues=[FCue(1, 10)]))
    flip = b"FLIP\x00" + (3).to_bytes(4, "big") + b"abc"
    payload = payload[:2] + flip + payload[2:]
    markers, warnings = parse_markers2_payload(payload)
    assert [c.index for c in markers.cues] == [1] and warnings == []


def test_truncated_entry_warns() -> None:
    payload = markers2_payload(FTrack(cues=[FCue(1, 10)]))[:-8]
    markers, warnings = parse_markers2_payload(payload)
    assert warnings


def test_malformed_cue_entry_is_skipped() -> None:
    payload = b"\x01\x01" + b"CUE\x00" + (3).to_bytes(4, "big") + b"\x00\x01\x02" + b"\x00"
    markers, warnings = parse_markers2_payload(payload)
    assert markers.cues == [] and "CUE" in warnings[0]


def test_bad_version_raises() -> None:
    with pytest.raises(MarkersError):
        decode_markers2(b"\x02\x01AAAA")


def test_b64_with_one_leftover_char() -> None:
    # Serato sometimes leaves a single trailing base64 character.
    encoded = base64.b64encode(b"\x01\x01hello").rstrip(b"=") + b"A"
    assert lenient_b64decode(encoded).startswith(b"\x01\x01hello")


def test_beatgrid_single_marker() -> None:
    (marker,) = decode_beatgrid(beatgrid_bytes([(0.125, 126.0)]))
    assert marker.position_s == pytest.approx(0.125)
    assert marker.bpm == pytest.approx(126.0)


def test_beatgrid_variable() -> None:
    grid = decode_beatgrid(beatgrid_bytes([(1.0, 16), (9.0, 120.0)]))
    assert grid[0].beats_to_next == 16
    assert segment_bpm(grid, 0) == pytest.approx(120.0)  # 16 beats in 8 s
    assert segment_bpm(grid, 1) == pytest.approx(120.0)


@pytest.mark.parametrize("raw", [b"", b"\x02\x00", b"\x01\x00\x00\x00\x00\x05\x00"])
def test_beatgrid_malformed(raw: bytes) -> None:
    with pytest.raises(BeatGridError):
        decode_beatgrid(raw)
