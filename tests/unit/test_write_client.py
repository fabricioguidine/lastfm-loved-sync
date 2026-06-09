import hashlib

import httpx
import pytest
import respx

from lastfm_loved_sync.config import Settings
from lastfm_loved_sync.lastfm_api import LastfmError, LastfmWriteClient, sign
from lastfm_loved_sync.models import Track


def test_sign_excludes_format_and_appends_secret():
    params = {"method": "track.love", "track": "Nude", "format": "json"}
    expected = hashlib.md5(b"methodtrack.lovetrackNudesecret").hexdigest()
    assert sign(params, "secret") == expected


@pytest.fixture
def write_settings(tmp_path) -> Settings:
    return Settings(
        api_key="k",
        shared_secret="s",
        session_key="sk",
        user="u",
        storage_state=tmp_path / "s.json",
    )


def test_write_client_requires_secret(tmp_path):
    settings = Settings(api_key="k", shared_secret="", storage_state=tmp_path / "s.json")
    with pytest.raises(LastfmError, match="SHARED_SECRET"):
        LastfmWriteClient(settings)


@respx.mock
async def test_get_token_and_authorize_url(write_settings: Settings):
    respx.get(write_settings.api_base).mock(
        return_value=httpx.Response(200, json={"token": "tok123"})
    )
    async with LastfmWriteClient(write_settings) as client:
        token = await client.get_token()
    assert token == "tok123"
    assert "token=tok123" in client.authorize_url(token)
    assert "api_key=k" in client.authorize_url(token)


@respx.mock
async def test_love_posts_signed_request(write_settings: Settings):
    route = respx.post(write_settings.api_base).mock(
        return_value=httpx.Response(200, json={"track": {}})
    )
    track = Track(artist="Radiohead", title="Nude", url="u")
    async with LastfmWriteClient(write_settings) as client:
        await client.love(track, loved=True)
    sent = dict(httpx.QueryParams(route.calls.last.request.content.decode()))
    assert sent["method"] == "track.love"
    assert sent["track"] == "Nude"
    assert sent["sk"] == "sk"
    assert sent["api_sig"] == sign(
        {k: v for k, v in sent.items() if k not in ("api_sig", "format")}, "s"
    )
