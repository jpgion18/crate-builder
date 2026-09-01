"""Fuzzy-match a pasted track list against a scanned local music library."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz, process

from crate_builder.input_parser import InputTrack
from crate_builder.library import Track

DEFAULT_THRESHOLD = 75

# How close (in WRatio points) a runner-up has to be to the top pick before
# it's flagged as a real toss-up rather than just noise below the winner —
# e.g. "Song (VIP Mix)" vs "Song (Club Mix)" both matching an input that just
# says "Song". Below this margin, auto-picking the top score is fine.
AMBIGUITY_MARGIN = 5
CANDIDATE_LIMIT = 5

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
    # Other library tracks that scored within AMBIGUITY_MARGIN of the top
    # pick and also clear the threshold — e.g. multiple remixes of the same
    # track. Only populated when `ambiguous` is True; empty otherwise so a
    # clean single match doesn't carry the extra payload.
    candidates: list[tuple[Track, float]] = field(default_factory=list)
    ambiguous: bool = False


def match_tracks(
    input_tracks: list[InputTrack],
    library_tracks: list[Track],
    threshold: int = DEFAULT_THRESHOLD,
) -> list[MatchResult]:
    """For each input track, find the best matching library track.

    A result is `matched=True` when the best candidate's score clears
    `threshold`; otherwise the best guess is still returned (for manual
    review) with `matched=False`. When two or more candidates are both
    genuine matches and close enough in score to be a toss-up (commonly
    different remixes/edits of the same track), `ambiguous=True` and
    `candidates` carries the close set for manual disambiguation instead of
    silently auto-picking one.
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

        top = process.extract(query, choices, scorer=fuzz.WRatio, limit=CANDIDATE_LIMIT)
        if not top:
            results.append(MatchResult(input=inp, track=None, score=0, matched=False))
            continue

        _, best_score, best_idx = top[0]
        matched = best_score >= threshold
        close_matches = [
            (library_tracks[idx], score)
            for _, score, idx in top
            if score >= threshold and best_score - score <= AMBIGUITY_MARGIN
        ]
        ambiguous = matched and len(close_matches) >= 2

        results.append(
            MatchResult(
                input=inp,
                track=library_tracks[best_idx],
                score=best_score,
                matched=matched,
                candidates=close_matches if ambiguous else [],
                ambiguous=ambiguous,
            )
        )

    return results
