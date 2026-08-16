"""Find likely-duplicate tracks in a scanned library.

Works with anything exposing `.artist`/`.title` — currently either
library.Track (a folder scan) or serato_database.SeratoDbTrack (Serato's
own database), whichever the caller passes in.

Two passes, in decreasing order of confidence:

1. Exact match after normalization (the same `normalize()`d "artist title"
   string) — catches the vast majority of real duplicates: the same song
   ripped twice, tagged slightly differently in case/punctuation, or saved
   in two file formats.
2. Fuzzy match within tracks that share the same normalized *title*. Title
   is grouped on exactly (not fuzzed) so this stays fast even on a large
   library — only tracks that already share an identical title get
   compared to each other, and that comparison is then fuzzy-scored on the
   full artist+title string to catch things like a missing or reordered
   featured-artist credit. This deliberately won't catch a typo'd
   *title* (it wouldn't land in the same bucket to begin with); scanning
   every track against every other track for that would turn an O(n)
   library scan into O(n^2), which doesn't scale to a real library.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from rapidfuzz import fuzz

from crate_builder.library import Track
from crate_builder.matcher import normalize
from crate_builder.serato_database import SeratoDbTrack

DEFAULT_FUZZY_THRESHOLD = 90

AnyTrack = Track | SeratoDbTrack


@dataclass
class DuplicateGroup:
    tracks: list[AnyTrack]
    reason: str  # "exact" or "fuzzy"


def find_duplicates(tracks: list[AnyTrack], fuzzy_threshold: int = DEFAULT_FUZZY_THRESHOLD) -> list[DuplicateGroup]:
    groups: list[DuplicateGroup] = []
    grouped_ids: set[int] = set()

    exact_buckets: dict[str, list[AnyTrack]] = defaultdict(list)
    for t in tracks:
        key = normalize(f"{t.artist} {t.title}")
        if key:
            exact_buckets[key].append(t)

    for bucket in exact_buckets.values():
        if len(bucket) > 1:
            groups.append(DuplicateGroup(tracks=bucket, reason="exact"))
            grouped_ids.update(id(t) for t in bucket)

    title_buckets: dict[str, list[AnyTrack]] = defaultdict(list)
    for t in tracks:
        if id(t) in grouped_ids:
            continue
        title_key = normalize(t.title)
        if title_key:
            title_buckets[title_key].append(t)

    for bucket in title_buckets.values():
        if len(bucket) < 2:
            continue
        for group in _fuzzy_group(bucket, fuzzy_threshold):
            if len(group) > 1:
                groups.append(DuplicateGroup(tracks=group, reason="fuzzy"))

    return groups


def _fuzzy_group(tracks: list[AnyTrack], threshold: int) -> list[list[AnyTrack]]:
    """Groups tracks within a single title-bucket by fuzzy artist+title score."""
    assigned: set[int] = set()
    result: list[list[AnyTrack]] = []
    for i, t in enumerate(tracks):
        if id(t) in assigned:
            continue
        query = normalize(f"{t.artist} {t.title}")
        group = [t]
        assigned.add(id(t))
        for other in tracks[i + 1 :]:
            if id(other) in assigned:
                continue
            candidate = normalize(f"{other.artist} {other.title}")
            if fuzz.WRatio(query, candidate) >= threshold:
                group.append(other)
                assigned.add(id(other))
        result.append(group)
    return result
