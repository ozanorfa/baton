"""`batonai runs` — run history of the current project."""

from pathlib import Path

import typer

from ai_orchestrator.cli import render
from ai_orchestrator.core.reporter import build_report
from ai_orchestrator.core.run_manager import RunManager

runs_app = typer.Typer(help="Browse this project's run history.", no_args_is_help=True)


@runs_app.command("list")
def list_runs() -> None:
    """All runs in this project, oldest first."""
    manager = RunManager(Path.cwd())
    run_ids = manager.list_run_ids()
    if not run_ids:
        render.console.print("no runs yet — try: batonai \"<request>\"")
        return
    rows = []
    for run_id in run_ids:
        state = manager.load_run(run_id)
        rows.append((state, build_report(state, manager)))
    render.render_runs_list(rows)


@runs_app.command("show")
def show_run(run_id: str = typer.Argument(..., help="Run id (see `batonai runs list`).")) -> None:
    """Per-stage detail of one run."""
    manager = RunManager(Path.cwd())
    try:
        state = manager.load_run(run_id)
    except FileNotFoundError as exc:
        render.render_error(str(exc))
        raise typer.Exit(code=2) from exc
    report = build_report(state, manager)
    render.console.print(f"[bold]request:[/bold] {state.request}")
    render.render_run_summary(state, manager.run_dir(run_id), report)
