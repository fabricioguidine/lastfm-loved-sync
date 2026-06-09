import httpx
import pytest
import respx

from lastfm_loved_sync.config import Settings
from lastfm_loved_sync.models import Track
from lastfm_loved_sync.playlists import (
    build_artist_playlists,
    build_genre_playlists,
    build_loved_playlist,
    build_period_playlist,
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
async def test_build_artist_playlists_uses_your_plays_for_favourite_artists(settings, tmp_path):
    def respond(request: httpx.Request) -> httpx.Response:
        m = request.url.params.get("method")
        if m == "user.getPersonalTags":
            return httpx.Response(
                200, json={"taggings": {"artists": {"artist": [{"name": "Mitski"}]}}}
            )
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
                                "playcount": "55",
                            },
                            {
                                "name": "Faint",
                                "url": "u3",
                                "artist": {"name": "Mitski"},
                                "playcount": "20",
                            },
                            {
                                "name": "Hot",
                                "url": "u4",
                                "artist": {"name": "Caroline Polachek"},
                                "playcount": "200",
                            },
                        ],
                        "@attr": {"totalPages": "1"},
                    }
                },
            )
        return httpx.Response(404, json={"error": 3, "message": "x"})

    respx.get(settings.api_base).mock(side_effect=respond)
    result = await build_artist_playlists(settings, tmp_path, tag="bookmarked", min_plays=50)
    # only Mitski is a favourite; only her >=50 plays tracks; the 20-play one excluded;
    # Caroline Polachek is not a favourite so no playlist for her.
    assert result == {"Mitski": 2}
    urls = [
        ln
        for ln in (tmp_path / "artist-mitski.m3u8").read_text(encoding="utf-8").splitlines()
        if ln.startswith("u")
    ]
    assert urls == ["u1", "u2"]


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


@respx.mock
async def test_build_genre_playlists_keeps_only_top_n(settings, tmp_path):
    def respond(request: httpx.Request) -> httpx.Response:
        m = request.url.params.get("method")
        if m == "user.getTopTracks":
            return httpx.Response(
                200,
                json={
                    "toptracks": {
                        "track": [
                            {
                                "name": "a",
                                "url": "u1",
                                "artist": {"name": "Pop1"},
                                "playcount": "300",
                            },
                            {
                                "name": "b",
                                "url": "u2",
                                "artist": {"name": "Rock1"},
                                "playcount": "100",
                            },
                            {
                                "name": "c",
                                "url": "u3",
                                "artist": {"name": "Jazz1"},
                                "playcount": "60",
                            },
                        ],
                        "@attr": {"totalPages": "1"},
                    }
                },
            )
        if m == "artist.getTopTags":
            artist = request.url.params.get("artist")
            return httpx.Response(200, json={"toptags": {"tag": [{"name": artist.lower()}]}})
        return httpx.Response(404, json={"error": 3, "message": "x"})

    respx.get(settings.api_base).mock(side_effect=respond)
    result = await build_genre_playlists(settings, tmp_path, min_plays=50, top=2)
    assert set(result) == {"pop1", "rock1"}  # jazz1 (lowest total plays) dropped
    assert not (tmp_path / "genre-jazz1.m3u8").exists()


@respx.mock
async def test_build_period_playlist_filters_by_plays(settings, tmp_path):
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("method") == "user.getWeeklyTrackChart":
            return httpx.Response(
                200,
                json={
                    "weeklytrackchart": {
                        "track": [
                            {
                                "name": "Big",
                                "url": "u1",
                                "artist": {"#text": "X"},
                                "playcount": "70",
                            },
                            {
                                "name": "Small",
                                "url": "u2",
                                "artist": {"#text": "Y"},
                                "playcount": "12",
                            },
                        ]
                    }
                },
            )
        return httpx.Response(404, json={"error": 3, "message": "x"})

    respx.get(settings.api_base).mock(side_effect=respond)
    added = await build_period_playlist(
        settings, tmp_path, from_ts=1000, to_ts=2000, min_plays=50, name="2026"
    )
    assert added == 1  # only the 70-play track clears the threshold
    assert "u1" in (tmp_path / "period-2026.m3u8").read_text(encoding="utf-8")


@respx.mock
async def test_build_loved_playlist(settings, tmp_path):
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("method") == "user.getLovedTracks":
            return httpx.Response(
                200,
                json={
                    "lovedtracks": {
                        "track": [
                            {"name": "Loved1", "url": "u1", "artist": {"name": "A"}},
                            {"name": "Loved2", "url": "u2", "artist": {"name": "B"}},
                        ],
                        "@attr": {"totalPages": "1"},
                    }
                },
            )
        return httpx.Response(404, json={"error": 3, "message": "x"})

    respx.get(settings.api_base).mock(side_effect=respond)
    added = await build_loved_playlist(settings, tmp_path)
    assert added == 2
    assert (tmp_path / "loved.m3u8").exists()
