from __future__ import annotations

from collections.abc import Awaitable, Callable

from .analysis import build_plan
from .browser import LoveAutomation, open_context
from .config import Settings
from .lastfm_api import LastfmClient
from .models import Action, PlannedChange, SyncPlan, Track

ProgressCb = Callable[[PlannedChange, bool], Awaitable[None] | None]


async def fetch_tracks(
    settings: Settings, *, top_limit: int = 1000, min_plays: int | None = None
) -> tuple[list[Track], list[Track]]:
    async with LastfmClient(settings) as client:
        top = await client.top_tracks(period="overall", limit=top_limit, min_plays=min_plays)
        loved = await client.loved_tracks()
    return top, loved


async def compute_plan(settings: Settings, min_plays: int) -> SyncPlan:
    top, loved = await fetch_tracks(settings, top_limit=1_000_000, min_plays=min_plays)
    return build_plan(top, loved, min_plays)


async def apply_plan(
    settings: Settings,
    plan: SyncPlan,
    *,
    headless: bool = True,
    progress: ProgressCb | None = None,
) -> int:
    """Apply every change through the browser. Returns the count of real clicks."""
    if plan.is_empty:
        return 0
    pw, context = await open_context(settings, headless=headless)
    clicks = 0
    try:
        automation = LoveAutomation(context, settings)
        for change in plan.changes:
            changed = await automation.apply(change.track, change.action)
            clicks += int(changed)
            if progress is not None:
                result = progress(change, changed)
                if result is not None:
                    await result
    finally:
        await context.close()
        await pw.stop()  # type: ignore[attr-defined]
    return clicks


__all__ = ["Action", "apply_plan", "compute_plan", "fetch_tracks"]
