import httpx
import pytest
import respx

from lastfm_loved_sync.config import Settings
from lastfm_loved_sync.models import Track
from lastfm_loved_sync.playlists import (
    build_artist_playlists,
    build_genre_playlists,
    merge_m3u,
)


def _tracks(*pairs):
    return [
        Track(artist=a, title=t, url=f"https://last.fm/{a}/{t}", playcount=pc) for a, t, pc in pairs
    ]


def test_merge_m3u_writes_and_is_idempotent(tmp_path):
    path = tmp_path / "p.m3u8"
    tracks = _tracks(("A", "x", 0), ("B", "y", 0))
    assert merge_m3u(path, tracks) == 2
    body = path.read_text(encoding="utf-8")
    assert body.startswith("#EXTM3U")
    assert "#EXTINF:-1,A - x" in body
    before = body
    assert merge_m3u(path, tracks) == 0  # idempotent
    assert path.read_text(encoding="utf-8") == before


def test_merge_m3u_appends_only_missing(tmp_path):
    path = tmp_path / "p.m3u8"
    merge_m3u(path, _tracks(("A", "x", 0)))
    added = merge_m3u(path, _tracks(("A", "x", 0), ("C", "z", 0)))
    assert added == 1
    urls = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.startswith("http")]
    assert urls == ["https://last.fm/A/x", "https://last.fm/C/z"]  # order preserved, no dupes


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(api_key="k", user="u", storage_state=tmp_path / "s.json")


@respx.mock
async def test_build_artist_playlists(settings, tmp_path):
    def respond(request: httpx.Request) -> httpx.Response:
        m = request.url.params.get("method")
        if m == "user.getPersonalTags":
            return httpx.Response(
                200, json={"taggings": {"artists": {"artist": [{"name": "Mitski"}]}}}
            )
        if m == "artist.getTopTracks":
            return httpx.Response(
                200,
                json={
                    "toptracks": {
                        "track": [
                            {
                                "name": "Nobody",
                                "url": "https://last.fm/Mitski/Nobody",
                                "artist": {"name": "Mitski"},
                            },
                        ]
                    }
                },
            )
        return httpx.Response(404, json={"error": 3, "message": "x"})

    respx.get(settings.api_base).mock(side_effect=respond)
    result = await build_artist_playlists(settings, tmp_path, tag="bookmarked", top_n=10)
    assert result == {"Mitski": 1}
    assert (tmp_path / "artist-mitski.m3u8").exists()


@respx.mock
async def test_build_genre_playlists_groups_by_artist_tag(settings, tmp_path):
    def respond(request: httpx.Request) -> httpx.Response:
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
                                "playcount": "80",
                            },
                            {
                                "name": "Faded",
                                "url": "u3",
                                "artist": {"name": "Low"},
                                "playcount": "10",
                            },
                        ],
                        "@attr": {"totalPages": "1"},
                    }
                },
            )
        if m == "artist.getTopTags":
            artist = request.url.params.get("artist")
            tag = "indie rock" if artist == "Mitski" else "slowcore"
            return httpx.Response(200, json={"toptags": {"tag": [{"name": tag}]}})
        return httpx.Response(404, json={"error": 3, "message": "x"})

    respx.get(settings.api_base).mock(side_effect=respond)
    result = await build_genre_playlists(settings, tmp_path, min_plays=50)
    assert result == {"indie rock": 2}  # the 10-play track is below threshold and excluded
    assert (tmp_path / "genre-indie-rock.m3u8").exists()
    assert not (tmp_path / "genre-slowcore.m3u8").exists()
