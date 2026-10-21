"""`batonai revise "<correction>"` — iterate on the last run without starting over (ADR-019).

Re-runs a completed run from the Coder (by default), carrying the prior run's
provider sessions forward so the Coder resumes its own session and treats the
correction as the next turn. Keeps the same run-id and reuses on-disk artifacts.
The correction is injected into the run's request so every re-run stage sees it.
"""

from pathlib import Path

import typer

from ai_orchestrator.cli import render
from ai_orchestrator.cli.commands import _shared as shared
from ai_orchestrator.core.run_manager import RunManager
from ai_orchestrator.transport.headless import HeadlessTransport


def revise(
    correction: str = typer.Argument(..., help="What to fix or change about the last run."),
    run_id: str = typer.Option(
        None, "--run", help="Revise this run instead of the most recent one."
    ),
    from_stage: str = typer.Option(
        None, "--from", help="Re-run from this stage instead of the coder (e.g. planner)."
    ),
    with_designer: bool = typer.Option(
        False, "--with-designer", help="Keep the Designer stage enabled (if the run used it)."
    ),
    with_tester: bool = typer.Option(
        False, "--with-tester", help="Keep the Tester stage enabled (if the run used it)."
    ),
    with_publisher: bool = typer.Option(
        False, "--with-publisher", help="Keep the Publisher stage enabled (if the run used it)."
    ),
) -> None:
    """Continue the last run with a correction — the Coder picks up where it left off."""
    project_dir = Path.cwd()
    manager = RunManager(project_dir)

    if not correction.strip():
        render.render_error("the correction is empty — say what should change.")
        raise typer.Exit(code=shared.EXIT_USAGE)

    if run_id is None:
        run_id = manager.latest_run_id()
        if run_id is None:
            render.render_error(
                'no runs to revise yet — start one with `batonai "<request>"`.'
            )
            raise typer.Exit(code=shared.EXIT_USAGE)

    try:
        state = manager.load_run(run_id)
    except FileNotFoundError as exc:
        render.render_error(str(exc))
        raise typer.Exit(code=shared.EXIT_USAGE) from exc

    loaded = shared.load_config_or_exit(
        project_dir,
        shared.stage_overrides(
            with_designer=with_designer, with_tester=with_tester, with_publisher=with_publisher
        ),
    )
    transport = HeadlessTransport()
    resolved = shared.preflight_or_exit(loaded, transport)
    shared.check_same_pipeline(state, resolved, "revise")

    render.console.print(f"[bold]revising[/bold] {run_id}: {correction}")
    engine, manager = shared.build_engine(project_dir, loaded, transport)
    state = shared.drive(
        lambda: engine.revise(state, resolved, correction, from_stage=from_stage), manager,
        run_id_hint=run_id,
    )
    shared.finish(state, manager)
