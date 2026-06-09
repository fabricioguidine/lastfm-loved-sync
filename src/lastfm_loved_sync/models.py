from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel

from .normalize import name_key, track_key


class Track(BaseModel):
    artist: str
    title: str
    url: str
    playcount: int = 0
    loved: bool = False

    @property
    def key(self) -> tuple[str, str]:
        return track_key(self.artist, self.title)

    def __str__(self) -> str:
        return f"{self.artist} - {self.title}"


class Artist(BaseModel):
    name: str
    playcount: int = 0

    @property
    def key(self) -> str:
        return name_key(self.name)

    def __str__(self) -> str:
        return self.name


class Album(BaseModel):
    artist: str
    title: str
    playcount: int = 0

    @property
    def key(self) -> tuple[str, str]:
        return track_key(self.artist, self.title)

    def __str__(self) -> str:
        return f"{self.artist} - {self.title}"


class Action(StrEnum):
    LOVE = "love"
    UNLOVE = "unlove"


class PlannedChange(BaseModel):
    track: Track
    action: Action


class SyncPlan(BaseModel):
    criterion: str
    to_love: list[Track]
    to_unlove: list[Track]

    @property
    def changes(self) -> list[PlannedChange]:
        return [PlannedChange(track=t, action=Action.LOVE) for t in self.to_love] + [
            PlannedChange(track=t, action=Action.UNLOVE) for t in self.to_unlove
        ]

    @property
    def is_empty(self) -> bool:
        return not self.to_love and not self.to_unlove
