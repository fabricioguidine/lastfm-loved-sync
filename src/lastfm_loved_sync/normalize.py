from __future__ import annotations

import unicodedata


def track_key(artist: str, title: str) -> tuple[str, str]:
    """Stable identity for a track across the read API and the loved list.

    mbids are frequently empty on Last.fm, so identity is the normalized
    (artist, title) pair: casefolded, unicode-normalized, whitespace-collapsed.
    """
    return (_norm(artist), _norm(title))


def _norm(value: str) -> str:
    folded = unicodedata.normalize("NFKC", value).casefold().strip()
    return " ".join(folded.split())
