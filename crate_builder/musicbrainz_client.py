"""Cross-check a track's tagged year against MusicBrainz's recording data.

Runs entirely server-side — unlike the browser-based concept this was
ported from, there's no CORS restriction to work around here (MusicBrainz's
own client library explicitly isn't built for direct browser use, which is
what necessitated a public CORS proxy in that prototype). A direct
server-side request needs none of that.

This never writes anything back to a file — it only reports what
MusicBrainz has on record, for a human to review and, if they agree, fix by
hand (via the Metadata Editor). MusicBrainz's own confidence score doesn't
reliably pick the right *specific recording* even at 100 — e.g. it can pick
a reissue/compilation's later date over the original release — so all 3 top
candidates are returned, not just the best one; don't collapse to a single
answer.
"""

from __future__ import annotations

import re

import requests

MUSICBRAINZ_URL = "https://musicbrainz.org/ws/2/recording/"
MIN_SCORE = 80
USER_AGENT = "CrateBuilder/1.0 (+https://github.com/jpgion18/crate-builder)"

# Pool/edit descriptors that live in the filename but were never part of the
# canonical recording title in MusicBrainz — strip before searching. Genuine
# remix/edit names (e.g. "R3HAB Remix") are deliberately kept, since the
# goal is that specific version's release date, not the original's.
_EDIT_SUFFIX_PATTERN = re.compile(
    r"\s*\((intro clean|clean extended|extended|clean|dirty|explicit|instrumental|radio edit|album version|main mix)\)",
    re.IGNORECASE,
)
# Multi-artist credits ("X ft Y & Z") rarely match MusicBrainz's exact credit
# string — search on just the primary (first-listed) artist instead.
_ARTIST_SPLIT_PATTERN = re.compile(r"\s+(ft\.?|feat\.?|featuring|vs\.?)\s+|,|&", re.IGNORECASE)


def clean_title_for_search(title: str) -> str:
    return _EDIT_SUFFIX_PATTERN.sub("", title or "").strip()


def primary_artist(artist: str) -> str:
    return _ARTIST_SPLIT_PATTERN.split(artist or "")[0].strip()


def _escape_quotes(text: str) -> str:
    return text.replace('"', '\\"')


def lookup_year(artist: str, title: str) -> dict:
    """Returns {status, mb_year, score, mb_link, candidates, note}.
    status is "matched" (a confident candidate was found — caller compares
    mb_year against the file's own tag to decide match vs. mismatch),
    "notfound", or "error"."""
    search_title = clean_title_for_search(title)
    search_artist = primary_artist(artist)
    query = f'recording:"{_escape_quotes(search_title)}" AND artist:"{_escape_quotes(search_artist)}"'

    try:
        response = requests.get(
            MUSICBRAINZ_URL,
            params={"query": query, "fmt": "json", "limit": 3},
            headers={"User-Agent": USER_AGENT},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        return _result("error", note=f"MusicBrainz request failed: {exc}")

    candidates = [
        {
            "mbid": r.get("id"),
            "year": (r.get("first-release-date") or "")[:4] or None,
            "score": r.get("score", 0),
            "link": f"https://musicbrainz.org/recording/{r.get('id')}",
        }
        for r in (data.get("recordings") or [])[:3]
    ]

    best = candidates[0] if candidates else None
    if not best:
        return _result("notfound", note=f'No match for "{search_artist} - {search_title}"')
    if best["score"] < MIN_SCORE:
        return _result("notfound", best, candidates, note=f"Best match too weak (score {best['score']})")
    if not best["year"]:
        return _result("notfound", best, candidates, note="Matched but no release date on record")

    return _result("matched", best, candidates)


def _result(status: str, best: dict | None = None, candidates: list | None = None, note: str = "") -> dict:
    return {
        "status": status,
        "mb_year": best["year"] if best else None,
        "score": best["score"] if best else None,
        "mb_link": best["link"] if best else None,
        "candidates": candidates or [],
        "note": note,
    }
