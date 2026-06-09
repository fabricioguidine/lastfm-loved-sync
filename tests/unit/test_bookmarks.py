import httpx
import pytest
import respx

from lastfm_loved_sync.bookmarks import (
    bookmark_artists,
    fetch_top_albums,
    fetch_top_artists,
)
from lastfm_loved_sync.config import Settings


@pytest.fixture
def write_settings(tmp_path) -> Settings:
    return Settings(
        api_key="k",
        shared_secret="s",
        session_key="sk",
        user="testuser",
        storage_state=tmp_path / "s.json",
    )


@respx.mock
async def test_fetch_top_artists_filters_below_threshold(write_settings, top_artists_json):
    respx.get(write_settings.api_base).mock(return_value=httpx.Response(200, json=top_artists_json))
    artists = await fetch_top_artists(write_settings, min_plays=1000)
    assert [(a.name, a.playcount) for a in artists] == [("Lady Gaga", 1500), ("Mitski", 1200)]


@respx.mock
async def test_fetch_top_albums_filters_below_threshold(write_settings, top_albums_json):
    respx.get(write_settings.api_base).mock(return_value=httpx.Response(200, json=top_albums_json))
    albums = await fetch_top_albums(write_settings, min_plays=1000)
    assert [(a.artist, a.title) for a in albums] == [("Lady Gaga", "Chromatica")]


@respx.mock
async def test_bookmark_artists_tags_and_reverifies(write_settings, top_artists_json):
    posted: list[dict] = []
    # getTags returns the tag, so the verify pass finds nothing to redo.
    tags_response = {"tags": {"tag": [{"name": "bookmarked"}]}}

    def respond(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            posted.append(dict(httpx.QueryParams(request.content.decode())))
            return httpx.Response(200, json={})
        method = request.url.params.get("method")
        if method == "user.getTopArtists":
            return httpx.Response(200, json=top_artists_json)
        if method == "artist.getTags":
            return httpx.Response(200, json=tags_response)
        return httpx.Response(404, json={"error": 3, "message": "unexpected"})

    respx.route(host="ws.audioscrobbler.com").mock(side_effect=respond)
    artists = await fetch_top_artists(write_settings, min_plays=1000)
    count = await bookmark_artists(write_settings, artists, "bookmarked")
    assert count == 2
    methods = [p["method"] for p in posted]
    assert methods == ["artist.addTags", "artist.addTags"]  # verify pass added none
    assert all(p["tags"] == "bookmarked" and p["sk"] == "sk" for p in posted)


async def test_bookmark_artists_requires_session(tmp_path, top_artists_json):
    from lastfm_loved_sync.models import Artist

    settings = Settings(
        api_key="k", shared_secret="s", session_key="", storage_state=tmp_path / "s.json"
    )
    with pytest.raises(RuntimeError, match="session key"):
        await bookmark_artists(settings, [Artist(name="X", playcount=2000)], "bookmarked")


@respx.mock
async def test_bookmark_skips_unresolvable_item_and_continues(write_settings):
    from lastfm_loved_sync.models import Artist

    def respond(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            params = dict(httpx.QueryParams(request.content.decode()))
            if params.get("artist") == "Ghost":  # Last.fm can't resolve this one
                return httpx.Response(200, json={"error": 6, "message": "Artist not found"})
            return httpx.Response(200, json={})
        return httpx.Response(200, json={"tags": {"tag": [{"name": "bookmarked"}]}})

    respx.route(host="ws.audioscrobbler.com").mock(side_effect=respond)
    artists = [Artist(name="Real", playcount=2000), Artist(name="Ghost", playcount=2000)]
    count = await bookmark_artists(write_settings, artists, "bookmarked")
    assert count == 1  # the unresolvable artist is skipped, the real one still tagged
