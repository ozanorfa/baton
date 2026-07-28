"""`batonai health` — show the repowise code-health slice, zero tokens.

The slice is injected into every stage prompt (ADR-025), but until now the only
place to read it was inside a run's `prompts/*.md` — and the `.repowise/` index
it comes from is deleted straight after use. That made a feature nobody could
inspect. This command answers "what does baton actually see?" on demand,
without a run and without spending anything.
"""

from pathlib import Path

import typer

from ai_orchestrator.cli import render
from ai_orchestrator.context.awareness import WorkspaceMode, detect_mode
from ai_orchestrator.context.health import cache_age_s, health_section


def _age_phrase(seconds: float) -> str:
    if seconds < 90:
        return "just now"
    if seconds < 5400:
        return f"{int(seconds // 60)}m ago"
    if seconds < 172800:
        return f"{int(seconds // 3600)}h ago"
    return f"{int(seconds // 86400)}d ago"


def health(
    refresh: bool = typer.Option(
        False, "--refresh", help="Recompute instead of using the cached analysis (ADR-028)."
    ),
) -> None:
    """Print the code-health hotspots baton would give every stage (no tokens)."""
    project_dir = Path.cwd()

    if detect_mode(project_dir) is WorkspaceMode.GREENFIELD:
        render.console.print(
            "[dim]greenfield project — no code history to score, so no health "
            "slice is produced (ADR-025).[/dim]"
        )
        return

    age = None if refresh else cache_age_s(project_dir)
    label = "reading cached analysis…" if age is not None else "running repowise health…"
    with render.console.status(f"[dim]{label}[/dim]"):
        section = health_section(project_dir, refresh=refresh)

    if not section:
        render.console.print(
            "no hotspots to report — either [bold]repowise[/bold] is not installed "
            "([dim]pipx install repowise[/dim]), or no source file crossed a concern "
            "threshold."
        )
        return

    render.console.print(section)
    # ADR-028: never present a stored reading as if it were current.
    if age is not None:
        render.console.print(
            f"\n[dim]from the cached analysis, computed {_age_phrase(age)} "
            "(.ai/health.json) — `batonai health --refresh` to recompute.[/dim]"
        )
    render.console.print(
        "\n[dim]this exact text is injected into every stage prompt when health is "
        "enabled (the wizard turns it on; scripted runs need --health).[/dim]"
    )
