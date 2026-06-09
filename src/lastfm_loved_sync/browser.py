from __future__ import annotations

from pathlib import Path

from playwright.async_api import BrowserContext, Page, async_playwright

from .config import Settings
from .models import Action, Track


class LoveAutomation:
    """Drives the Last.fm web UI to love/unlove tracks via a saved session.

    Each action is idempotent: it reads the button's current state and only
    clicks when the desired state differs, so re-running a plan is safe.
    """

    def __init__(self, context: BrowserContext, settings: Settings) -> None:
        self._context = context
        self._selectors = settings.selectors

    async def apply(self, track: Track, action: Action) -> bool:
        """Ensure ``track`` matches ``action``. Returns True if a click happened."""
        page = await self._context.new_page()
        try:
            await page.goto(track.url, wait_until="domcontentloaded")
            return await self._toggle(page, want_loved=action is Action.LOVE)
        finally:
            await page.close()

    async def _toggle(self, page: Page, *, want_loved: bool) -> bool:
        button = page.locator(self._selectors.love_button).first
        await button.wait_for(state="visible")
        if await self._is_loved(page) == want_loved:
            return False
        await button.click()
        await page.wait_for_function(
            "([sel, want]) => {"
            "  const m = document.querySelector(sel);"
            "  return Boolean(m) === want;"
            "}",
            arg=[self._selectors.loved_marker, want_loved],
        )
        return True

    async def _is_loved(self, page: Page) -> bool:
        return await page.locator(self._selectors.loved_marker).count() > 0


async def open_context(
    settings: Settings, *, headless: bool = True
) -> tuple[object, BrowserContext]:
    """Launch Chromium with the saved login session. Caller must close both."""
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=headless)
    state = settings.storage_state
    context = await browser.new_context(storage_state=str(state) if state.exists() else None)
    return pw, context


async def save_login(settings: Settings) -> Path:
    """Open a headed browser for manual login, then persist the session."""
    pw = await async_playwright().start()
    try:
        browser = await pw.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(settings.login_url, wait_until="domcontentloaded")
        await page.wait_for_url("**/user/**", timeout=180_000)
        await context.storage_state(path=str(settings.storage_state))
        await browser.close()
        return settings.storage_state
    finally:
        await pw.stop()
