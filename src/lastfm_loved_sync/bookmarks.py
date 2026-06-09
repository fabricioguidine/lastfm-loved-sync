from __future__ import annotations

from collections.abc import Awaitable, Callable

from .api import LastfmClient, LastfmWriteClient
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
    async with LastfmWriteClient(settings) as writer, LastfmClient(settings) as reader:
        for artist in artists:
            await writer.tag_artist(artist.name, tag)
            await _emit(progress, artist.name)
        for artist in artists:
            if wanted not in await reader.artist_tags(artist.name):
                await writer.tag_artist(artist.name, tag)
    return len(artists)


async def bookmark_albums(
    settings: Settings, albums: list[Album], tag: str, *, progress: BookmarkCb | None = None
) -> int:
    """Apply ``tag`` to each album, then re-check and re-tag any that didn't take."""
    if not albums:
        return 0
    _require_session(settings)
    wanted = tag.casefold()
    async with LastfmWriteClient(settings) as writer, LastfmClient(settings) as reader:
        for album in albums:
            await writer.tag_album(album.artist, album.title, tag)
            await _emit(progress, str(album))
        for album in albums:
            if wanted not in await reader.album_tags(album.artist, album.title):
                await writer.tag_album(album.artist, album.title, tag)
    return len(albums)


def _require_session(settings: Settings) -> None:
    if not settings.session_key:
        raise RuntimeError("No session key. Run `lastfm-loved-sync auth` first.")


async def _emit(progress: BookmarkCb | None, name: str) -> None:
    if progress is not None:
        result = progress(name)
        if result is not None:
            await result
