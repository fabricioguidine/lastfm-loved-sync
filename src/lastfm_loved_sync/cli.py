from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import typer

from . import tui
from .analysis import build_plan
from .api_apply import fetch_session_key, request_token
from .browser import save_login
from .config import Settings
from .sync import apply_plan, apply_until_synced, fetch_tracks

app = typer.Typer(
    add_completion=False,
    help="Love your most-played Last.fm tracks and unlove the under-played ones.",
)


@app.callback()
def _main() -> None:
    # Windows consoles default to cp1252 and choke on unicode track names.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def _settings() -> Settings:
    settings = Settings()
    missing = [n for n in ("api_key", "user") if not getattr(settings, n)]
    if missing:
        raise typer.BadParameter(
            f"Missing LASTFM_{'/'.join(m.upper() for m in missing)}. "
            "Set them in .env (see .env.example)."
        )
    return settings


@app.command()
def login() -> None:
    """Open a browser to log in once and save the session for automation."""
    settings = Settings()
    path = asyncio.run(save_login(settings))
    tui.console.print(f"[green]Session saved to {path}[/green]")


def _persist_session_key(key: str, env_file: Path = Path(".env")) -> None:
    lines = env_file.read_text().splitlines() if env_file.exists() else []
    lines = [ln for ln in lines if not ln.startswith("LASTFM_SESSION_KEY=")]
    lines.append(f"LASTFM_SESSION_KEY={key}")
    env_file.write_text("\n".join(lines) + "\n")


@app.command()
def auth() -> None:
    """Authorize via the Last.fm token flow and save a session key to .env."""
    settings = Settings()
    if not settings.api_key or not settings.shared_secret:
        raise typer.BadParameter("Set LASTFM_API_KEY and LASTFM_SHARED_SECRET in .env first.")
    token, url = asyncio.run(request_token(settings))
    tui.console.print(f"Open this URL and click [bold]Yes, allow access[/bold]:\n\n  {url}\n")
    typer.confirm("Authorized?", abort=True)
    key = asyncio.run(fetch_session_key(settings, token))
    _persist_session_key(key)
    tui.console.print("[green]Session key saved to .env. You can now run `sync --apply`.[/green]")


_SECRET_KEYS = ("LASTFM_SESSION_KEY", "LASTFM_SHARED_SECRET", "LASTFM_API_KEY")


@app.command()
def logout(
    purge: bool = typer.Option(
        False, "--purge", help="Also remove the API key and shared secret, not just the session key"
    ),
    env_file: Path = Path(".env"),
) -> None:
    """Delete saved credentials from .env (the session key, or everything with --purge)."""
    targets = _SECRET_KEYS if purge else ("LASTFM_SESSION_KEY",)
    if env_file.exists():
        kept = [ln for ln in env_file.read_text().splitlines() if not ln.startswith(targets)]
        env_file.write_text("\n".join(kept) + "\n" if kept else "")
    Settings().storage_state.unlink(missing_ok=True)
    tui.console.print(f"[green]Removed {', '.join(targets)} from {env_file}.[/green]")
    if purge:
        tui.console.print(
            "Also delete the API application itself at "
            "[bold]https://www.last.fm/api/accounts[/bold]."
        )


@app.command()
def sync(
    min_plays: int | None = typer.Option(
        None, "--min-plays", "-m", help="Love every track with at least this many scrobbles"
    ),
    apply: bool = typer.Option(False, "--apply", help="Apply changes (default: dry-run)"),
    headful: bool = typer.Option(False, help="Show the browser while applying"),
) -> None:
    """Love tracks at or above the scrobble threshold, unlove those below (dry-run by default)."""
    settings = _settings()
    asyncio.run(_sync(settings, min_plays, apply, headful))


async def _sync(settings: Settings, min_plays: int | None, apply: bool, headful: bool) -> None:
    threshold = min_plays if min_plays is not None else tui.prompt_min_plays()
    full, loved = await fetch_tracks(settings, top_limit=1_000_000, min_plays=threshold)
    plan = build_plan(full, loved, threshold)
    tui.render_plan(plan)
    if plan.is_empty or not apply:
        if not apply and not plan.is_empty:
            tui.console.print("[yellow]Dry-run. Re-run with --apply to make changes.[/yellow]")
        return
    if not tui.confirm_apply(plan):
        tui.console.print("[yellow]Aborted.[/yellow]")
        return

    def _progress(change, changed):  # type: ignore[no-untyped-def]
        mark = "✓" if changed else "·"
        tui.console.print(f"  {mark} {change.action.value} {change.track}")

    if settings.session_key:
        clicks = await apply_until_synced(settings, threshold, progress=_progress)
    else:
        clicks = await apply_plan(settings, plan, headless=not headful, progress=_progress)
    tui.console.print(f"[green]Done — {clicks} changes applied.[/green]")


__all__ = ["app"]
