import httpx
import pytest
import respx

from lastfm_loved_sync.config import Settings
from lastfm_loved_sync.lastfm_api import LastfmClient, LastfmError


@respx.mock
async def test_top_tracks_parsed_and_ranked(settings: Settings, api_responder):
    respx.get(settings.api_base).mock(side_effect=api_responder)
    async with LastfmClient(settings) as client:
        tracks = await client.top_tracks(limit=10)
    assert [t.title for t in tracks] == ["Reckoner", "Roygbiv", "Xtal", "Archangel", "Angel Echoes"]
    assert tracks[0].playcount == 500
    assert tracks[0].artist == "Radiohead"


@respx.mock
async def test_loved_tracks_flagged(settings: Settings, api_responder):
    respx.get(settings.api_base).mock(side_effect=api_responder)
    async with LastfmClient(settings) as client:
        loved = await client.loved_tracks()
    assert {t.title for t in loved} == {"Reckoner", "Xtal", "Old Favourite"}
    assert all(t.loved for t in loved)


@respx.mock
async def test_api_error_is_raised(settings: Settings):
    respx.get(settings.api_base).mock(
        return_value=httpx.Response(200, json={"error": 10, "message": "Invalid API key"})
    )
    async with LastfmClient(settings) as client:
        with pytest.raises(LastfmError, match="Invalid API key"):
            await client.top_tracks()


async def test_missing_api_key_raises(tmp_path):
    settings = Settings(api_key="", user="u", storage_state=tmp_path / "s.json")
    async with LastfmClient(settings) as client:
        with pytest.raises(LastfmError, match="LASTFM_API_KEY"):
            await client.top_tracks()
