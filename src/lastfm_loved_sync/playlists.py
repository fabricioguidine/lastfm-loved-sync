from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from pathlib import Path

from .api import LastfmClient
from .config import Settings
from .models import Track
from .normalize import name_key

ProgressCb = Callable[[str, int], Awaitable[None] | None]


def _slug(name: str) -> str:
    s = re.sub(r"[^\w\s-]", "", name, flags=re.UNICODE).strip().lower()
    return re.sub(r"[\s_-]+", "-", s) or "untitled"


def _parse_m3u(path: Path) -> list[tuple[str, str]]:
    """Existing (url, label) entries, in order."""
    if not path.exists():
        return []
    entries: list[tuple[str, str]] = []
    label = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith("#EXTINF"):
            label = s.split(",", 1)[1] if "," in s else ""
        elif s and not s.startswith("#"):
            entries.append((s, label))
            label = ""
    return entries


def merge_m3u(path: Path, tracks: list[Track]) -> int:
    """Append tracks not already in the playlist (by URL). Returns the count added.

    Idempotent: re-running with the same tracks leaves the file untouched and
    returns 0. Existing entries and their order are preserved.
    """
    existing = _parse_m3u(path)
    have = {url for url, _ in existing}
    added = [(t.url, f"{t.artist} - {t.title}") for t in tracks if t.url and t.url not in have]
    if not added and path.exists():
        return 0
    lines = ["#EXTM3U"]
    for url, label in existing + added:
        lines.append(f"#EXTINF:-1,{label}")
        lines.append(url)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(added)


async def artist_groups(
    settings: Settings, *, tag: str = "bookmarked", min_plays: int = 50
) -> list[tuple[str, list[Track]]]:
    """(artist, tracks) for each favourite (tagged) artist, holding your tracks by
    that artist at or above ``min_plays`` scrobbles."""
    async with LastfmClient(settings) as client:
        favourites = {name_key(n): n for n in await client.personal_tag_artists(tag)}
        top = await client.top_tracks(limit=1_000_000, min_plays=min_plays)
    groups: dict[str, list[Track]] = {}
    for track in top:
        if track.playcount < min_plays:
            continue
        display = favourites.get(name_key(track.artist))
        if display is not None:
            groups.setdefault(display, []).append(track)
    return list(groups.items())


async def genre_groups(
    settings: Settings, *, min_plays: int = 50, top: int = 5
) -> list[tuple[str, list[Track]]]:
    """(genre, tracks) for the ``top`` genres by total plays, holding your tracks at
    or above ``min_plays`` scrobbles. Genre is the artist's dominant Last.fm tag."""
    async with LastfmClient(settings) as client:
        tracks = await client.top_tracks(limit=1_000_000, min_plays=min_plays)
        tag_cache: dict[str, str] = {}
        groups: dict[str, list[Track]] = {}
        for track in tracks:
            if track.playcount < min_plays:
                continue
            key = track.artist.casefold()
            if key not in tag_cache:
                tag_cache[key] = await client.artist_top_tag(track.artist) or "untagged"
            groups.setdefault(tag_cache[key], []).append(track)
    ranked = sorted(groups, key=lambda g: sum(t.playcount for t in groups[g]), reverse=True)
    return [(g, groups[g]) for g in ranked[:top]]


async def build_artist_playlists(
    settings: Settings,
    out_dir: Path,
    *,
    tag: str = "bookmarked",
    min_plays: int = 50,
    progress: ProgressCb | None = None,
) -> dict[str, int]:
    """Write one local playlist per favourite artist (your tracks at/above the threshold)."""
    result: dict[str, int] = {}
    for name, tracks in await artist_groups(settings, tag=tag, min_plays=min_plays):
        added = merge_m3u(out_dir / f"artist-{_slug(name)}.m3u8", tracks)
        result[name] = added
        await _emit(progress, name, added)
    return result


async def build_genre_playlists(
    settings: Settings,
    out_dir: Path,
    *,
    min_plays: int = 50,
    top: int = 5,
    progress: ProgressCb | None = None,
) -> dict[str, int]:
    """Write one local playlist for each of the top genres (your tracks at/above the threshold)."""
    result: dict[str, int] = {}
    for genre, tracks in await genre_groups(settings, min_plays=min_plays, top=top):
        added = merge_m3u(out_dir / f"genre-{_slug(genre)}.m3u8", tracks)
        result[genre] = added
        await _emit(progress, genre, added)
    return result


async def build_period_playlist(
    settings: Settings,
    out_dir: Path,
    *,
    from_ts: int,
    to_ts: int,
    min_plays: int = 50,
    name: str = "since",
) -> int:
    """One playlist of your tracks scrobbled at least ``min_plays`` times within
    the [from_ts, to_ts] window."""
    async with LastfmClient(settings) as client:
        tracks = await client.tracks_in_period(from_ts, to_ts)
    qualifying = [t for t in tracks if t.playcount >= min_plays]
    return merge_m3u(out_dir / f"period-{_slug(name)}.m3u8", qualifying)


async def build_loved_playlist(settings: Settings, out_dir: Path) -> int:
    """One playlist of all your loved (favourite) tracks."""
    async with LastfmClient(settings) as client:
        loved = await client.loved_tracks()
    return merge_m3u(out_dir / "loved.m3u8", loved)


async def _emit(progress: ProgressCb | None, name: str, added: int) -> None:
    if progress is not None:
        outcome = progress(name, added)
        if outcome is not None:
            await outcome
