from lastfm_loved_sync.models import SyncPlan, Track
from lastfm_loved_sync.tui import _valid_min_plays, render_plan


def test_valid_min_plays_rejects_non_positive_and_non_digits():
    assert isinstance(_valid_min_plays("abc"), str)
    assert isinstance(_valid_min_plays("0"), str)
    assert _valid_min_plays("100") is True


def test_render_plan_runs_for_changes_and_empty(capsys):
    track = Track(artist="A", title="T", url="u")
    render_plan(SyncPlan(criterion=">=100 plays", to_love=[track], to_unlove=[]))
    render_plan(SyncPlan(criterion=">=100 plays", to_love=[], to_unlove=[]))
    out = capsys.readouterr().out
    assert "LOVE" in out
    assert "sync" in out.lower()
