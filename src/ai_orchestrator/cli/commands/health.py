"""`batonai health` — show the repowise code-health slice, zero tokens.

The slice is injected into every stage prompt (ADR-025), but until now the only
place to read it was inside a run's `prompts/*.md` — and the `.repowise/` index
it comes from is deleted straight after use. That made a feature nobody could
inspect. This command answers "what does baton actually see?" on demand,
without a run and without spending anything.
"""

from pathlib import Path

from ai_orchestrator.cli import render
from ai_orchestrator.context.awareness import WorkspaceMode, detect_mode
from ai_orchestrator.context.health import health_section


def health() -> None:
    """Print the code-health hotspots baton would give every stage (no tokens)."""
    project_dir = Path.cwd()

    if detect_mode(project_dir) is WorkspaceMode.GREENFIELD:
        render.console.print(
            "[dim]greenfield project — no code history to score, so no health "
            "slice is produced (ADR-025).[/dim]"
        )
        return

    with render.console.status("[dim]running repowise health…[/dim]"):
        section = health_section(project_dir)

    if not section:
        render.console.print(
            "no hotspots to report — either [bold]repowise[/bold] is not installed "
            "([dim]pipx install repowise[/dim]), or no source file crossed a concern "
            "threshold."
        )
        return

    render.console.print(section)
    render.console.print(
        "\n[dim]this exact text is injected into every stage prompt when health is "
        "enabled (the wizard turns it on; scripted runs need --health).[/dim]"
    )
