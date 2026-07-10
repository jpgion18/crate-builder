"""Fuzzy-match a pasted track list against a scanned local music library."""

from __future__ import annotations

import re
from dataclasses import dataclass

from rapidfuzz import fuzz, process

from crate_builder.input_parser import InputTrack
from crate_builder.library import Track

DEFAULT_THRESHOLD = 75

_NOISE_PATTERN = re.compile(
    r"\((?:feat|ft|featuring|prod|radio edit|clean|explicit|official)[^)]*\)"
    r"|\[(?:feat|ft|featuring|prod|radio edit|clean|explicit|official)[^\]]*\]"
    r"|\b(?:official|audio|video|lyrics?|hd|hq)\b",
    re.IGNORECASE,
)
_PUNCTUATION_PATTERN = re.compile(r"[^\w\s]")
_WHITESPACE_PATTERN = re.compile(r"\s+")


def normalize(text: str) -> str:
    text = text.lower()
    text = _NOISE_PATTERN.sub(" ", text)
    text = _PUNCTUATION_PATTERN.sub(" ", text)
    text = _WHITESPACE_PATTERN.sub(" ", text)
    return text.strip()


@dataclass
class MatchResult:
    input: InputTrack
    track: Track | None
    score: float
    matched: bool


def match_tracks(
    input_tracks: list[InputTrack],
    library_tracks: list[Track],
    threshold: int = DEFAULT_THRESHOLD,
) -> list[MatchResult]:
    """For each input track, find the best matching library track.

    A result is `matched=True` when the best candidate's score clears
    `threshold`; otherwise the best guess is still returned (for manual
    review) with `matched=False`.
    """
    if not library_tracks:
        return [MatchResult(input=t, track=None, score=0, matched=False) for t in input_tracks]

    choices = {
        i: normalize(f"{t.artist} {t.title}") for i, t in enumerate(library_tracks)
    }

    results: list[MatchResult] = []
    for inp in input_tracks:
        query = normalize(f"{inp.artist} {inp.title}".strip())
        if not query:
            results.append(MatchResult(input=inp, track=None, score=0, matched=False))
            continue

        best = process.extractOne(query, choices, scorer=fuzz.WRatio)
        if best is None:
            results.append(MatchResult(input=inp, track=None, score=0, matched=False))
            continue

        _, score, idx = best
        results.append(
            MatchResult(
                input=inp,
                track=library_tracks[idx],
                score=score,
                matched=score >= threshold,
            )
        )

    return results
