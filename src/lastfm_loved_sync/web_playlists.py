from __future__ import annotations

import re
from collections.abc import Awaitable, Callable

from playwright.async_api import BrowserContext, Page

from .browser import open_context
from .config import Settings
from .models import Track

ProgressCb = Callable[[str, int], Awaitable[None] | None]

# Last.fm has no playlist API. These drive the web endpoints behind the playlist
# UI through a logged-in browser session. Free accounts cap at 8 playlists and
# roughly 250 tracks each; the 250 cap is silent (extra adds return OK but do
# nothing), so we stop at PER_PLAYLIST_CAP to avoid pointless requests.
MAX_PLAYLISTS = 8
PER_PLAYLIST_CAP = 250

_CREATE_JS = """async () => {
    const forms = [...document.querySelectorAll('form')];
    const f = forms.find(x => (x.getAttribute('action') || '').endsWith('/playlists'));
    if (!f) return '';
    const r = await fetch(f.getAttribute('action'), {method: 'POST', body: new FormData(f),
        headers: {'X-Requested-With': 'XMLHttpRequest'}, credentials: 'same-origin'});
    return r.url;
}"""

_POST_JS = """async ([action, fields]) => {
    const fd = new FormData();
    for (const k in fields) fd.append(k, fields[k]);
    const r = await fetch(action, {method: 'POST', body: fd,
        headers: {'X-Requested-With': 'XMLHttpRequest'}, credentials: 'same-origin'});
    let text = ''; try { text = await r.text(); } catch (e) {}
    return {status: r.status, limit: /track limit/i.test(text)};
}"""


class WebPlaylistClient:
    """Create, rename, fill and delete Last.fm playlists via a browser session."""

    def __init__(self, context: BrowserContext, settings: Settings) -> None:
        self._context = context
        self._base = f"https://www.last.fm/user/{settings.user}/playlists"
        self._page: Page | None = None

    async def _ready(self, url: str) -> Page:
        if self._page is None:
            self._page = await self._context.new_page()
        await self._page.goto(url, wait_until="domcontentloaded")
        return self._page

    async def _csrf(self) -> str:
        page = self._page
        assert page is not None
        token: str = await page.evaluate(
            "() => (document.querySelector('input[name=csrfmiddlewaretoken]') || {}).value || ''"
        )
        return token

    async def list_ids(self) -> list[str]:
        page = await self._ready(self._base)
        return sorted(set(re.findall(r"/playlists/(\d+)", await page.content())))

    async def create(self) -> str | None:
        page = await self._ready(self._base + "/create")
        url: str = await page.evaluate(_CREATE_JS)
        pid = url.rstrip("/").split("/")[-1]
        return pid if pid.isdigit() else None

    async def rename(self, pid: str, title: str) -> None:
        await self._ready(f"{self._base}/{pid}")
        page = self._page
        assert page is not None
        await page.evaluate(
            _POST_JS,
            [f"{self._base}/{pid}", {"csrfmiddlewaretoken": await self._csrf(), "title": title}],
        )

    async def add_track(self, pid: str, track: Track, csrf: str) -> bool:
        page = self._page
        assert page is not None
        result = await page.evaluate(
            _POST_JS,
            [
                f"{self._base}/{pid}/entries",
                {
                    "csrfmiddlewaretoken": csrf,
                    "track": track.title,
                    "artist": track.artist,
                    "ajax": "1",
                },
            ],
        )
        return bool(result["status"] < 400 and not result["limit"])

    async def delete(self, pid: str) -> None:
        await self._ready(f"{self._base}/{pid}")
        page = self._page
        assert page is not None
        await page.evaluate(
            _POST_JS,
            [
                f"{self._base}/{pid}",
                {"csrfmiddlewaretoken": await self._csrf(), "action": "delete"},
            ],
        )

    async def fill(self, pid: str, title: str, tracks: list[Track]) -> int:
        """Rename to ``title`` and add up to PER_PLAYLIST_CAP tracks. Returns the count added."""
        await self.rename(pid, title)
        csrf = await self._csrf()
        added = 0
        for track in tracks[:PER_PLAYLIST_CAP]:
            if await self.add_track(pid, track, csrf):
                added += 1
        return added


async def push_playlists(
    settings: Settings,
    named: list[tuple[str, list[Track]]],
    *,
    replace: bool = True,
    progress: ProgressCb | None = None,
) -> dict[str, int]:
    """Create one Last.fm playlist per (title, tracks) pair, capped at MAX_PLAYLISTS.

    With ``replace`` the account's existing playlists are deleted first (the free
    8-playlist cap leaves no room otherwise).
    """
    pw, context = await open_context(settings, headless=True)
    result: dict[str, int] = {}
    try:
        client = WebPlaylistClient(context, settings)
        if replace:
            for existing in await client.list_ids():
                await client.delete(existing)
        for title, tracks in named[:MAX_PLAYLISTS]:
            pid = await client.create()
            if pid is None:
                continue
            added = await client.fill(pid, title, tracks)
            result[title] = added
            if progress is not None:
                outcome = progress(title, added)
                if outcome is not None:
                    await outcome
    finally:
        await context.close()
        await pw.stop()  # type: ignore[attr-defined]
    return result
