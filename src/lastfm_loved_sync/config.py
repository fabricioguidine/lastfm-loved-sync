from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Selectors(BaseSettings):
    """CSS selectors for the Last.fm track-page love control.

    Kept in config because Last.fm's markup changes over time; the e2e fixture
    mirrors these defaults so the click mechanism is always covered by a test.
    """

    love_button: str = "button.love-button"
    loved_marker: str = ".love-button--loved, [data-loved='true']"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="LASTFM_", extra="ignore")

    api_key: str = Field(default="", description="Last.fm read API key")
    user: str = Field(default="", description="Last.fm username")
    storage_state: Path = Field(default=Path("storage_state.json"))
    api_base: str = "https://ws.audioscrobbler.com/2.0/"
    login_url: str = "https://www.last.fm/login"
    request_timeout: float = 20.0
    selectors: Selectors = Field(default_factory=Selectors)
