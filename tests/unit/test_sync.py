from lastfm_loved_sync.config import Settings
from lastfm_loved_sync.models import SyncPlan
from lastfm_loved_sync.sync import apply_plan


async def test_apply_plan_empty_skips_browser(settings: Settings):
    # An empty plan must not launch a browser; it returns zero clicks.
    plan = SyncPlan(criterion=">=100 plays", to_love=[], to_unlove=[])
    assert await apply_plan(settings, plan) == 0
