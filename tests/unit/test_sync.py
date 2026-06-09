import lastfm_loved_sync.sync as sync_module
from lastfm_loved_sync.config import Settings
from lastfm_loved_sync.models import SyncPlan, Track
from lastfm_loved_sync.sync import apply_plan, apply_until_synced


async def test_apply_plan_empty_skips_browser(settings: Settings):
    # An empty plan must not launch a browser; it returns zero clicks.
    plan = SyncPlan(criterion=">=100 plays", to_love=[], to_unlove=[])
    assert await apply_plan(settings, plan) == 0


async def test_apply_until_synced_reapplies_until_empty(settings: Settings, monkeypatch):
    # Round 1 leaves a leftover (a write that didn't stick); round 2 clears it.
    plans = [
        SyncPlan(
            criterion="c",
            to_love=[Track(artist="A", title="x", url="u"), Track(artist="A", title="y", url="v")],
            to_unlove=[],
        ),
        SyncPlan(criterion="c", to_love=[Track(artist="A", title="y", url="v")], to_unlove=[]),
        SyncPlan(criterion="c", to_love=[], to_unlove=[]),
    ]
    monkeypatch.setattr(sync_module, "compute_plan", lambda *a, **k: _pop(plans))

    applied = []

    async def fake_apply(_settings, plan, *, progress=None):
        applied.append(len(plan.changes))
        return len(plan.changes)

    monkeypatch.setattr(sync_module, "apply_plan_api", fake_apply)
    total = await apply_until_synced(settings, 100)
    assert applied == [2, 1]  # shrinks each round, then the empty plan stops the loop
    assert total == 3


async def test_apply_until_synced_stops_when_no_progress(settings: Settings, monkeypatch):
    stuck = SyncPlan(criterion="c", to_love=[Track(artist="A", title="x", url="u")], to_unlove=[])
    monkeypatch.setattr(sync_module, "compute_plan", lambda *a, **k: _const(stuck))

    rounds = []

    async def fake_apply(_settings, plan, *, progress=None):
        rounds.append(1)
        return len(plan.changes)

    monkeypatch.setattr(sync_module, "apply_plan_api", fake_apply)
    await apply_until_synced(settings, 100, max_rounds=5)
    assert len(rounds) == 1  # second round sees no progress and bails


async def _pop(seq):
    return seq.pop(0)


async def _const(value):
    return value
