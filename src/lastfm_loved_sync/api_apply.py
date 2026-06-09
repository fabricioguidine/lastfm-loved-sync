from __future__ import annotations

from collections.abc import Awaitable, Callable

from .config import Settings
from .lastfm_api import LastfmWriteClient
from .models import Action, PlannedChange, SyncPlan

ProgressCb = Callable[[PlannedChange, bool], Awaitable[None] | None]


async def request_token(settings: Settings) -> tuple[str, str]:
    """Return (token, authorize_url) for the manual one-click grant."""
    async with LastfmWriteClient(settings) as client:
        token = await client.get_token()
        return token, client.authorize_url(token)


async def fetch_session_key(settings: Settings, token: str) -> str:
    """Exchange an authorized token for a session key."""
    async with LastfmWriteClient(settings) as client:
        return await client.get_session(token)


async def apply_plan_api(
    settings: Settings, plan: SyncPlan, *, progress: ProgressCb | None = None
) -> int:
    """Apply every change through the authenticated API. Returns the count applied."""
    if plan.is_empty:
        return 0
    if not settings.session_key:
        raise RuntimeError("No session key. Run `lastfm-loved-sync auth` first.")
    applied = 0
    async with LastfmWriteClient(settings) as client:
        for change in plan.changes:
            await client.love(change.track, loved=change.action is Action.LOVE)
            applied += 1
            if progress is not None:
                result = progress(change, True)
                if result is not None:
                    await result
    return applied
