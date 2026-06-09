from __future__ import annotations

from .models import SyncPlan, Track


def _diff(target: list[Track], loved_tracks: list[Track], criterion: str) -> SyncPlan:
    """Two-way diff to make the loved set equal ``target``."""
    target_keys = {t.key for t in target}
    loved_keys = {t.key for t in loved_tracks}
    to_love = [t for t in target if t.key not in loved_keys]
    to_unlove = [t for t in loved_tracks if t.key not in target_keys]
    return SyncPlan(criterion=criterion, to_love=to_love, to_unlove=to_unlove)


def build_plan(top_tracks: list[Track], loved_tracks: list[Track], min_plays: int) -> SyncPlan:
    """Love every track with at least ``min_plays`` scrobbles; unlove the rest.

    A loved track is unloved unless it clears the threshold: any loved track at
    or above ``min_plays`` appears in ``top_tracks`` (the full play-ranked list),
    so the set difference correctly drops loved tracks that fall below it.
    """
    if min_plays < 1:
        raise ValueError("min_plays must be a positive integer")
    target = [t for t in top_tracks if t.playcount >= min_plays]
    return _diff(target, loved_tracks, f">={min_plays} plays")
