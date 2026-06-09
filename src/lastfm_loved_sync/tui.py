from __future__ import annotations

import questionary
from rich.console import Console
from rich.table import Table

from .models import Album, Artist, SyncPlan

console = Console()


def _valid_min_plays(value: str) -> bool | str:
    if not value.isdigit() or int(value) < 1:
        return "Enter a positive whole number"
    return True


def prompt_min_plays(default: int = 100) -> int:
    answer = questionary.text(
        "Love every track with at least how many scrobbles?",
        default=str(default),
        validate=_valid_min_plays,
    ).ask()
    if answer is None:
        raise KeyboardInterrupt
    return int(answer)


def confirm_apply(plan: SyncPlan) -> bool:
    answer = questionary.confirm(
        f"Apply {len(plan.to_love)} loves and {len(plan.to_unlove)} unloves?",
        default=False,
    ).ask()
    return bool(answer)


def render_plan(plan: SyncPlan) -> None:
    if plan.is_empty:
        console.print("[green]Already in sync, nothing to do.[/green]")
        return
    table = Table(title=f"Sync preview ({plan.criterion})")
    table.add_column("Action", style="bold")
    table.add_column("Artist")
    table.add_column("Title")
    for track in plan.to_love:
        table.add_row("[green]LOVE[/green]", track.artist, track.title)
    for track in plan.to_unlove:
        table.add_row("[red]UNLOVE[/red]", track.artist, track.title)
    console.print(table)
    console.print(
        f"[green]+{len(plan.to_love)} love[/green]  [red]-{len(plan.to_unlove)} unlove[/red]"
    )


def render_bookmarks(artists: list[Artist], albums: list[Album], tag: str) -> None:
    if not artists and not albums:
        console.print("[green]Nothing above the threshold to tag.[/green]")
        return
    table = Table(title=f"Bookmark preview (tag: {tag})")
    table.add_column("Kind", style="bold")
    table.add_column("Name")
    table.add_column("Plays", justify="right")
    for artist in artists:
        table.add_row("ARTIST", artist.name, str(artist.playcount))
    for album in albums:
        table.add_row("ALBUM", f"{album.artist} - {album.title}", str(album.playcount))
    console.print(table)
    console.print(f"[green]{len(artists)} artists, {len(albums)} albums[/green]")
