from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .config import Settings
from .models import Track


class LastfmError(RuntimeError):
    pass


class LastfmClient:
    """Read-only Last.fm API client (top tracks + loved tracks)."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._client = client or httpx.AsyncClient(timeout=settings.request_timeout)
        self._owns_client = client is None

    async def __aenter__(self) -> LastfmClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._owns_client:
            await self._client.aclose()

    @retry(
        retry=retry_if_exception_type(httpx.TransportError),
        wait=wait_exponential(multiplier=0.5, max=8),
        stop=stop_after_attempt(4),
        reraise=True,
    )
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
        """Top tracks ranked by playcount.

        With ``min_plays`` set, pagination stops once playcounts drop below the
        threshold (the list is sorted descending), so a high ``limit`` is safe.
        """
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

    async def _paginate(
        self,
        method: str,
        *,
        container: str,
        limit: int,
        extra: dict[str, str],
        build: Any,
        stop_below: int | None = None,
    ) -> list[Track]:
        page_size = min(200, limit)
        tracks: list[Track] = []
        page = 1
        while len(tracks) < limit:
            data = await self._call(method, limit=page_size, page=page, **extra)
            body = data.get(container, {})
            rows = body.get("track", [])
            if isinstance(rows, dict):
                rows = [rows]
            tracks.extend(build(r) for r in rows)
            total_pages = int(body.get("@attr", {}).get("totalPages", page))
            if page >= total_pages or not rows:
                break
            if stop_below is not None and tracks[-1].playcount < stop_below:
                break
            page += 1
        return tracks[:limit]
