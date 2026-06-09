"""End-to-end of the native playlist client against a route-mocked Last.fm.

No real account: Playwright route interception serves the create page, the
create redirect, the playlist page (with a csrf token) and the entries
endpoint, so the full create -> rename -> add path runs in a real Chromium and
we assert the right requests are issued.
"""

from __future__ import annotations

import pytest
from playwright.async_api import Route, async_playwright

from lastfm_loved_sync.config import Settings
from lastfm_loved_sync.models import Track
from lastfm_loved_sync.web_playlists import WebPlaylistClient

pytestmark = pytest.mark.e2e

BASE = "https://www.last.fm/user/testuser/playlists"
_FORM = '<input name="csrfmiddlewaretoken" value="tok">'
_ACTION = "/user/testuser/playlists"
CREATE_HTML = f'<html><body><form action="{_ACTION}" method="post">{_FORM}</form></body></html>'
PLAYLIST_HTML = f"<html><body>{_FORM}</body></html>"


def _make_handler(entries: list[str]):
    async def handler(route: Route) -> None:
        req = route.request
        url = req.url.split("?")[0]
        if req.method == "POST" and url.endswith("/entries"):
            entries.append(req.post_data or "")
            await route.fulfill(status=200, content_type="application/json", body="{}")
        elif req.method == "POST" and url.endswith("/playlists"):  # create
            await route.fulfill(status=302, headers={"location": BASE + "/999"})
        elif req.method == "GET" and url.endswith("/create"):
            await route.fulfill(status=200, content_type="text/html", body=CREATE_HTML)
        elif "/playlists/999" in url:  # GET page or POST rename
            await route.fulfill(status=200, content_type="text/html", body=PLAYLIST_HTML)
        else:
            await route.fulfill(status=200, content_type="text/html", body=PLAYLIST_HTML)

    return handler


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(api_key="k", user="testuser", storage_state=tmp_path / "s.json")


async def test_e2e_create_and_fill_issues_expected_requests(settings):
    entries: list[str] = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        context = await browser.new_context()
        await context.route("**/user/testuser/**", _make_handler(entries))
        client = WebPlaylistClient(context, settings)

        pid = await client.create()
        assert pid == "999"

        tracks = [
            Track(artist="Mitski", title="Nobody", url="u1"),
            Track(artist="Charli XCX", title="Von dutch", url="u2"),
        ]
        added = await client.fill(pid, "pop", tracks)
        await browser.close()

    assert added == 2
    assert len(entries) == 2
    assert "Nobody" in entries[0] and "Mitski" in entries[0]
    assert "Von+dutch" in entries[1].replace("%20", "+") or "Von dutch" in entries[1]
