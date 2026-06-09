import pytest

from lastfm_loved_sync.analysis import build_plan
from lastfm_loved_sync.models import Track


def _top() -> list[Track]:
    return [
        Track(artist="Radiohead", title="Reckoner", url="u1", playcount=500),
        Track(artist="Boards of Canada", title="Roygbiv", url="u2", playcount=400),
        Track(artist="Aphex Twin", title="Xtal", url="u3", playcount=300),
        Track(artist="Burial", title="Archangel", url="u4", playcount=200),
    ]


def _loved() -> list[Track]:
    return [
        Track(artist="Radiohead", title="Reckoner", url="u1", loved=True),
        Track(artist="Aphex Twin", title="Xtal", url="u3", loved=True),
        Track(artist="Some Artist", title="Old Favourite", url="u9", loved=True),
    ]


def test_threshold_loves_unloved_above_and_unloves_loved_below():
    plan = build_plan(_top(), _loved(), min_plays=300)
    assert [t.title for t in plan.to_love] == ["Roygbiv"]
    assert [t.title for t in plan.to_unlove] == ["Old Favourite"]
    assert plan.criterion == ">=300 plays"


def test_lower_threshold_pulls_in_more_tracks():
    plan = build_plan(_top(), _loved(), min_plays=200)
    assert {t.title for t in plan.to_love} == {"Roygbiv", "Archangel"}
    assert [t.title for t in plan.to_unlove] == ["Old Favourite"]


def test_higher_threshold_unloves_below_it():
    plan = build_plan(_top(), _loved(), min_plays=450)
    assert plan.to_love == []
    assert {t.title for t in plan.to_unlove} == {"Xtal", "Old Favourite"}


def test_already_synced_is_empty():
    top = [Track(artist="Radiohead", title="Reckoner", url="u1", playcount=500)]
    loved = [Track(artist="Radiohead", title="Reckoner", url="u1", loved=True)]
    assert build_plan(top, loved, min_plays=100).is_empty


def test_non_positive_threshold_raises():
    with pytest.raises(ValueError):
        build_plan(_top(), _loved(), min_plays=0)
