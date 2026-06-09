from __future__ import annotations

import questionary
from rich.console import Console
from rich.table import Table

from .models import SyncPlan

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
        console.print("[green]Already in sync — nothing to do.[/green]")
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
