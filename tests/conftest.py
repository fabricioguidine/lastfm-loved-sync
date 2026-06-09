from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from lastfm_loved_sync.config import Settings

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def top_tracks_json() -> dict[str, Any]:
    return _load("top_tracks.json")


@pytest.fixture
def loved_tracks_json() -> dict[str, Any]:
    return _load("loved_tracks.json")


@pytest.fixture
def top_artists_json() -> dict[str, Any]:
    return _load("top_artists.json")


@pytest.fixture
def top_albums_json() -> dict[str, Any]:
    return _load("top_albums.json")


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        api_key="test-key",
        user="testuser",
        storage_state=tmp_path / "storage_state.json",
    )


@pytest.fixture
def track_page_html() -> str:
    return (FIXTURES / "track_page.html").read_text(encoding="utf-8")


@pytest.fixture
def api_responder(top_tracks_json: dict[str, Any], loved_tracks_json: dict[str, Any]):
    """respx side-effect that dispatches by the Last.fm ``method`` query param."""

    def respond(request: httpx.Request) -> httpx.Response:
        method = request.url.params.get("method")
        if method == "user.getTopTracks":
            return httpx.Response(200, json=top_tracks_json)
        if method == "user.getLovedTracks":
            return httpx.Response(200, json=loved_tracks_json)
        return httpx.Response(404, json={"error": 3, "message": "unknown method"})

    return respond
