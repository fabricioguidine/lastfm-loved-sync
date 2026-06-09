from __future__ import annotations

from typing import Any

import httpx

from ..config import Settings
from ..models import Track
from .errors import LastfmError
from .resilience import resilient
from .sign import sign


class LastfmWriteClient:
    """Authenticated Last.fm client: token auth, track.love/unlove, artist/album tagging."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        if not settings.api_key or not settings.shared_secret:
            raise LastfmError("LASTFM_API_KEY and LASTFM_SHARED_SECRET must be set")
        self._settings = settings
        self._client = client or httpx.AsyncClient(timeout=settings.request_timeout)
        self._owns_client = client is None

    async def __aenter__(self) -> LastfmWriteClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _signed(self, **params: str) -> dict[str, str]:
        params = {"api_key": self._settings.api_key, **params}
        params["api_sig"] = sign(params, self._settings.shared_secret)
        params["format"] = "json"
        return params

    @resilient
    async def _request(self, http_method: str, **params: str) -> dict[str, Any]:
        signed = self._signed(**params)
        if http_method == "POST":
            resp = await self._client.post(self._settings.api_base, data=signed)
        else:
            resp = await self._client.get(self._settings.api_base, params=signed)
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        if "error" in data:
            raise LastfmError(f"Last.fm error {data['error']}: {data.get('message')}")
        return data

    async def get_token(self) -> str:
        data = await self._request("GET", method="auth.getToken")
        return str(data["token"])

    def authorize_url(self, token: str) -> str:
        return f"{self._settings.auth_url}?api_key={self._settings.api_key}&token={token}"

    async def get_session(self, token: str) -> str:
        data = await self._request("GET", method="auth.getSession", token=token)
        return str(data["session"]["key"])

    async def love(self, track: Track, *, loved: bool) -> None:
        await self._request(
            "POST",
            method="track.love" if loved else "track.unlove",
            track=track.title,
            artist=track.artist,
            sk=self._settings.session_key,
        )

    async def tag_artist(self, name: str, tag: str) -> None:
        await self._request(
            "POST", method="artist.addTags", artist=name, tags=tag, sk=self._settings.session_key
        )

    async def tag_album(self, artist: str, album: str, tag: str) -> None:
        await self._request(
            "POST",
            method="album.addTags",
            artist=artist,
            album=album,
            tags=tag,
            sk=self._settings.session_key,
        )
