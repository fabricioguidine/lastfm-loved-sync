"""End-to-end of the API write path against a stateful in-memory Last.fm.

No network or real account. A respx side-effect models the server's state
(loved set, personal tags) and deliberately *drops the first write* for each
item, so these tests prove the convergence/re-verify logic actually recovers
from the silent write losses that motivated it.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from lastfm_loved_sync.bookmarks import bookmark_artists
from lastfm_loved_sync.config import Settings
from lastfm_loved_sync.models import Artist
from lastfm_loved_sync.sync import apply_until_synced

pytestmark = pytest.mark.e2e


@pytest.fixture
def api_settings(tmp_path) -> Settings:
    return Settings(
        api_key="k",
        shared_secret="s",
        session_key="sk",
        user="testuser",
        storage_state=tmp_path / "s.json",
    )


class FakeLastfm:
    """Tiny stateful Last.fm. The first write to any key is silently dropped."""

    def __init__(self, top_tracks: list[tuple[str, str, int]], loved: set[tuple[str, str]]):
        self.top = top_tracks
        self.loved = set(loved)
        self.tags: dict[str, set[str]] = {}
        self._seen_writes: set[str] = set()

    def _dropped(self, marker: str) -> bool:
        if marker in self._seen_writes:
            return False
        self._seen_writes.add(marker)
        return True  # drop the first attempt only

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return self._write(dict(httpx.QueryParams(request.content.decode())))
        return self._read(request.url.params)

    def _read(self, params) -> httpx.Response:
        method = params.get("method")
        if method == "user.getTopTracks":
            rows = [
                {"artist": {"name": a}, "name": t, "url": f"u/{a}/{t}", "playcount": str(pc)}
                for a, t, pc in self.top
            ]
            return httpx.Response(
                200, json={"toptracks": {"track": rows, "@attr": {"totalPages": "1"}}}
            )
        if method == "user.getLovedTracks":
            rows = [{"artist": {"name": a}, "name": t, "url": f"u/{a}/{t}"} for a, t in self.loved]
            return httpx.Response(
                200, json={"lovedtracks": {"track": rows, "@attr": {"totalPages": "1"}}}
            )
        if method == "artist.getTags":
            names = sorted(self.tags.get(params.get("artist"), set()))
            return httpx.Response(200, json={"tags": {"tag": [{"name": n} for n in names]}})
        return httpx.Response(404, json={"error": 3, "message": f"unexpected {method}"})

    def _write(self, body) -> httpx.Response:
        method = body["method"]
        if method in ("track.love", "track.unlove"):
            key = (body["artist"], body["track"])
            if not self._dropped(f"{method}:{key}"):
                self.loved.add(key) if method == "track.love" else self.loved.discard(key)
        elif method == "artist.addTags":
            marker = f"tag:{body['artist']}:{body['tags']}"
            if not self._dropped(marker):
                self.tags.setdefault(body["artist"], set()).add(body["tags"])
        return httpx.Response(200, json={})


async def test_e2e_sync_converges_despite_dropped_writes(api_settings):
    # Three tracks >=100 plays; two already loved (one of them below threshold).
    server = FakeLastfm(
        top_tracks=[("A", "x", 500), ("B", "y", 300), ("C", "z", 50)],
        loved={("C", "z"), ("D", "old")},  # both below threshold -> must be unloved
    )
    with respx.mock:
        respx.route(host="ws.audioscrobbler.com").mock(side_effect=server)
        await apply_until_synced(api_settings, 100)
    # Final loved set equals the >=100 target exactly, despite first-write drops.
    assert server.loved == {("A", "x"), ("B", "y")}


async def test_e2e_bookmark_reapplies_dropped_tag(api_settings):
    server = FakeLastfm(top_tracks=[], loved=set())
    with respx.mock:
        respx.route(host="ws.audioscrobbler.com").mock(side_effect=server)
        artists = [Artist(name="A", playcount=2000), Artist(name="B", playcount=1500)]
        await bookmark_artists(api_settings, artists, "bookmarked")
    # Even though each artist's first addTags was dropped, the verify pass fixed it.
    assert server.tags == {"A": {"bookmarked"}, "B": {"bookmarked"}}
