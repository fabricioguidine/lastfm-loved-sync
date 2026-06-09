from pathlib import Path

import pytest
from typer.testing import CliRunner

from lastfm_loved_sync import cli
from lastfm_loved_sync.config import Settings
from lastfm_loved_sync.models import Track

runner = CliRunner()


@pytest.fixture
def patch_settings(monkeypatch, tmp_path: Path):
    def _patch(*, api_key: str = "k", user: str = "u") -> None:
        monkeypatch.setattr(
            cli,
            "Settings",
            lambda: Settings(api_key=api_key, user=user, storage_state=tmp_path / "s.json"),
        )

    return _patch


def test_sync_errors_without_credentials(patch_settings):
    patch_settings(api_key="", user="")
    result = runner.invoke(cli.app, ["sync", "--min-plays", "100"])
    assert result.exit_code != 0
    assert "Missing" in result.output


def test_sync_dry_run_makes_no_changes(patch_settings, monkeypatch):
    patch_settings()
    top = [
        Track(artist="A", title="T1", url="u1", playcount=150),
        Track(artist="B", title="T2", url="u2", playcount=120),
    ]
    loved = [Track(artist="C", title="Old", url="u9", loved=True)]

    async def fake_fetch(_settings, *, top_limit=1_000_000, min_plays=None):
        return top, loved

    # apply_plan must never run in a dry-run; make it explode if called.
    async def boom(*_args, **_kwargs):
        raise AssertionError("apply_plan called during dry-run")

    monkeypatch.setattr(cli, "fetch_tracks", fake_fetch)
    monkeypatch.setattr(cli, "apply_plan", boom)
    result = runner.invoke(cli.app, ["sync", "--min-plays", "100"])
    assert result.exit_code == 0, result.output
    assert "Dry-run" in result.output
