from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

import httpx

from ..config import Settings
from ..models import Album, Artist, Track
from .errors import LastfmError
from .resilience import resilient

T = TypeVar("T")


class LastfmClient:
    """Read-only Last.fm API client (top tracks/artists/albums, loved tracks, tags)."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._client = client or httpx.AsyncClient(timeout=settings.request_timeout)
        self._owns_client = client is None

    async def __aenter__(self) -> LastfmClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._owns_client:
            await self._client.aclose()

    @resilient
    async def _call(self, method: str, **params: str | int) -> dict[str, Any]:
        if not self._settings.api_key:
            raise LastfmError("LASTFM_API_KEY is not set")
        query = {
            "method": method,
            "user": self._settings.user,
            "api_key": self._settings.api_key,
            "format": "json",
            **params,
        }
        resp = await self._client.get(self._settings.api_base, params=query)
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        if "error" in data:
            raise LastfmError(f"Last.fm error {data['error']}: {data.get('message')}")
        return data

    async def top_tracks(
        self, *, period: str = "overall", limit: int = 1000, min_plays: int | None = None
    ) -> list[Track]:
        """Top tracks ranked by playcount (pagination stops below ``min_plays``)."""
        return await self._paginate(
            "user.getTopTracks",
            container="toptracks",
            limit=limit,
            extra={"period": period},
            stop_below=min_plays,
            build=lambda raw: Track(
                artist=raw["artist"]["name"],
                title=raw["name"],
                url=raw["url"],
                playcount=int(raw.get("playcount", 0)),
            ),
        )

    async def loved_tracks(self, *, limit: int = 5000) -> list[Track]:
        """All loved tracks."""
        return await self._paginate(
            "user.getLovedTracks",
            container="lovedtracks",
            limit=limit,
            extra={},
            build=lambda raw: Track(
                artist=raw["artist"]["name"],
                title=raw["name"],
                url=raw["url"],
                loved=True,
            ),
        )

    async def top_artists(
        self, *, period: str = "overall", limit: int = 1000, min_plays: int | None = None
    ) -> list[Artist]:
        """Top artists ranked by scrobble count (pagination stops below ``min_plays``)."""
        return await self._paginate(
            "user.getTopArtists",
            container="topartists",
            limit=limit,
            extra={"period": period},
            stop_below=min_plays,
            row_key="artist",
            build=lambda raw: Artist(name=raw["name"], playcount=int(raw.get("playcount", 0))),
        )

    async def top_albums(
        self, *, period: str = "overall", limit: int = 1000, min_plays: int | None = None
    ) -> list[Album]:
        """Top albums ranked by play count (pagination stops below ``min_plays``)."""
        return await self._paginate(
            "user.getTopAlbums",
            container="topalbums",
            limit=limit,
            extra={"period": period},
            stop_below=min_plays,
            row_key="album",
            build=lambda raw: Album(
                artist=raw["artist"]["name"],
                title=raw["name"],
                playcount=int(raw.get("playcount", 0)),
            ),
        )

    async def artist_tags(self, name: str) -> set[str]:
        """The user's own tags on an artist (casefolded)."""
        data = await self._call("artist.getTags", artist=name)
        return _tag_names(data.get("tags", {}))

    async def album_tags(self, artist: str, album: str) -> set[str]:
        """The user's own tags on an album (casefolded)."""
        data = await self._call("album.getTags", artist=artist, album=album)
        return _tag_names(data.get("tags", {}))

    async def _paginate(
        self,
        method: str,
        *,
        container: str,
        limit: int,
        extra: dict[str, str],
        build: Callable[[dict[str, Any]], T],
        stop_below: int | None = None,
        row_key: str = "track",
    ) -> list[T]:
        page_size = min(200, limit)
        items: list[T] = []
        page = 1
        while len(items) < limit:
            data = await self._call(method, limit=page_size, page=page, **extra)
            body = data.get(container, {})
            rows = body.get(row_key, [])
            if isinstance(rows, dict):
                rows = [rows]
            items.extend(build(r) for r in rows)
            total_pages = int(body.get("@attr", {}).get("totalPages", page))
            if page >= total_pages or not rows:
                break
            if stop_below is not None and _playcount(items[-1]) < stop_below:
                break
            page += 1
        return items[:limit]


def _playcount(item: Any) -> int:
    return int(getattr(item, "playcount", 0))


def _tag_names(tags_body: Any) -> set[str]:
    if not isinstance(tags_body, dict):
        return set()
    rows = tags_body.get("tag", [])
    if isinstance(rows, dict):
        rows = [rows]
    return {row["name"].casefold() for row in rows}
