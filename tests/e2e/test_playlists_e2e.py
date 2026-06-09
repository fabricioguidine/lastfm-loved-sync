"""End-to-end of the local-playlist path: read via a mocked API, write .m3u8
files, then re-run and confirm the append-only idempotency holds.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from lastfm_loved_sync.config import Settings
from lastfm_loved_sync.playlists import build_genre_playlists

pytestmark = pytest.mark.e2e


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(api_key="k", user="u", storage_state=tmp_path / "s.json")


def _responder(request: httpx.Request) -> httpx.Response:
    m = request.url.params.get("method")
    if m == "user.getTopTracks":
        return httpx.Response(
            200,
            json={
                "toptracks": {
                    "track": [
                        {
                            "name": "Nobody",
                            "url": "u1",
                            "artist": {"name": "Mitski"},
                            "playcount": "120",
                        },
                        {
                            "name": "Geyser",
                            "url": "u2",
                            "artist": {"name": "Mitski"},
                            "playcount": "60",
                        },
                    ],
                    "@attr": {"totalPages": "1"},
                }
            },
        )
    if m == "artist.getTopTags":
        return httpx.Response(200, json={"toptags": {"tag": [{"name": "indie rock"}]}})
    return httpx.Response(404, json={"error": 3, "message": "x"})


@respx.mock
async def test_e2e_genre_playlists_generate_then_idempotent(settings, tmp_path):
    respx.get(settings.api_base).mock(side_effect=_responder)

    first = await build_genre_playlists(settings, tmp_path, min_plays=50)
    assert first == {"indie rock": 2}
    playlist = tmp_path / "genre-indie-rock.m3u8"
    snapshot = playlist.read_text(encoding="utf-8")
    assert snapshot.count("#EXTINF") == 2

    second = await build_genre_playlists(settings, tmp_path, min_plays=50)
    assert second == {"indie rock": 0}  # nothing new on re-run
    assert playlist.read_text(encoding="utf-8") == snapshot  # file untouched
