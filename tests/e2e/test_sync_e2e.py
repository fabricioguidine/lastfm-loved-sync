"""End-to-end: mocked Last.fm API + a real Chromium driving a local love button.

No network and no real account are touched. respx serves the API JSON, and
Playwright route-interception serves a local HTML fixture whose love button
behaves like Last.fm's, so the full read -> plan -> browser-write path runs for real.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx
from playwright.async_api import Route, async_playwright

from lastfm_loved_sync.analysis import build_plan
from lastfm_loved_sync.browser import LoveAutomation
from lastfm_loved_sync.config import Settings
from lastfm_loved_sync.models import Action
from lastfm_loved_sync.sync import fetch_tracks

pytestmark = pytest.mark.e2e

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def _page_html(template: str, *, loved: bool) -> str:
    return template.replace("__LOVED_CLASS__", "love-button--loved" if loved else "").replace(
        "__LOVED_ATTR__", "true" if loved else "false"
    )


def _make_router(template: str, initial_loved: dict[str, bool]):
    async def handler(route: Route) -> None:
        url = route.request.url.split("?")[0]
        loved = initial_loved.get(url, False)
        await route.fulfill(
            status=200,
            content_type="text/html",
            body=_page_html(template, loved=loved),
        )

    return handler


async def _plan(settings: Settings):
    with respx.mock(assert_all_called=False) as mock:

        def respond(request):  # type: ignore[no-untyped-def]
            method = request.url.params.get("method")
            name = "top_tracks" if method == "user.getTopTracks" else "loved_tracks"
            return httpx.Response(200, json=_load(name))

        mock.get(settings.api_base).mock(side_effect=respond)
        top, loved = await fetch_tracks(settings)
    # Fixture playcounts: 500/400/300/200/100. Threshold 300 -> target = top three,
    # so Roygbiv (unloved) is loved and Old Favourite (below) is unloved.
    return build_plan(top, loved, min_plays=300)


async def test_e2e_applies_two_way_sync(settings: Settings, track_page_html: str):
    plan = await _plan(settings)
    assert {t.title for t in plan.to_love} == {"Roygbiv"}
    assert {t.title for t in plan.to_unlove} == {"Old Favourite"}

    # Each target page starts in the OPPOSITE of its desired state -> a click is needed.
    initial = {c.track.url: c.action is Action.UNLOVE for c in plan.changes}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        context = await browser.new_context()
        await context.route("**/music/**", _make_router(track_page_html, initial))
        automation = LoveAutomation(context, settings)

        clicks = [await automation.apply(c.track, c.action) for c in plan.changes]
        assert clicks == [True, True]
        await browser.close()


async def test_e2e_idempotent_when_already_in_state(settings: Settings, track_page_html: str):
    plan = await _plan(settings)
    # Each page already matches its desired state -> no click should happen.
    initial = {c.track.url: c.action is Action.LOVE for c in plan.changes}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        context = await browser.new_context()
        await context.route("**/music/**", _make_router(track_page_html, initial))
        automation = LoveAutomation(context, settings)

        clicks = [await automation.apply(c.track, c.action) for c in plan.changes]
        assert clicks == [False, False]
        await browser.close()
