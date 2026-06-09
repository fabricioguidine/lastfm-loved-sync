from __future__ import annotations

from collections.abc import Awaitable, Callable

from .api import LastfmClient, LastfmError, LastfmWriteClient
from .config import Settings
from .models import Album, Artist

BookmarkCb = Callable[[str], Awaitable[None] | None]


async def fetch_top_artists(settings: Settings, min_plays: int) -> list[Artist]:
    async with LastfmClient(settings) as client:
        artists = await client.top_artists(limit=1_000_000, min_plays=min_plays)
    return [a for a in artists if a.playcount >= min_plays]


async def fetch_top_albums(settings: Settings, min_plays: int) -> list[Album]:
    async with LastfmClient(settings) as client:
        albums = await client.top_albums(limit=1_000_000, min_plays=min_plays)
    return [a for a in albums if a.playcount >= min_plays]


async def bookmark_artists(
    settings: Settings, artists: list[Artist], tag: str, *, progress: BookmarkCb | None = None
) -> int:
    """Apply ``tag`` to each artist, then re-check and re-tag any that didn't take."""
    if not artists:
        return 0
    _require_session(settings)
    wanted = tag.casefold()
    tagged = 0
    async with LastfmWriteClient(settings) as writer, LastfmClient(settings) as reader:
        for artist in artists:
            if await _safe_tag(writer.tag_artist(artist.name, tag)):
                tagged += 1
                await _emit(progress, artist.name)
        for artist in artists:
            tags = await _safe_read(reader.artist_tags(artist.name))
            if tags is not None and wanted not in tags:
                await _safe_tag(writer.tag_artist(artist.name, tag))
    return tagged


async def bookmark_albums(
    settings: Settings, albums: list[Album], tag: str, *, progress: BookmarkCb | None = None
) -> int:
    """Apply ``tag`` to each album, then re-check and re-tag any that didn't take."""
    if not albums:
        return 0
    _require_session(settings)
    wanted = tag.casefold()
    tagged = 0
    async with LastfmWriteClient(settings) as writer, LastfmClient(settings) as reader:
        for album in albums:
            if await _safe_tag(writer.tag_album(album.artist, album.title, tag)):
                tagged += 1
                await _emit(progress, str(album))
        for album in albums:
            tags = await _safe_read(reader.album_tags(album.artist, album.title))
            if tags is not None and wanted not in tags:
                await _safe_tag(writer.tag_album(album.artist, album.title, tag))
    return tagged


def _require_session(settings: Settings) -> None:
    if not settings.session_key:
        raise RuntimeError("No session key. Run `lastfm-loved-sync auth` first.")


async def _safe_tag(coro: Awaitable[None]) -> bool:
    """A single tag write; a track/album Last.fm can't resolve is skipped, not fatal."""
    try:
        await coro
        return True
    except LastfmError:
        return False


async def _safe_read(coro: Awaitable[set[str]]) -> set[str] | None:
    try:
        return await coro
    except LastfmError:
        return None


async def _emit(progress: BookmarkCb | None, name: str) -> None:
    if progress is not None:
        result = progress(name)
        if result is not None:
            await result
