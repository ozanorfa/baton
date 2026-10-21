"""`batonai resume <run-id>` — continue a failed run from its failed stage,
reusing every artifact that already succeeded (T33)."""

from pathlib import Path

import typer

from ai_orchestrator.cli import render
from ai_orchestrator.cli.commands import _shared as shared
from ai_orchestrator.core.run_manager import RunManager
from ai_orchestrator.transport.headless import HeadlessTransport


def resume(
    run_id: str = typer.Argument(..., help="Run id (see `batonai runs list`)."),
    from_stage: str = typer.Option(
        None, "--from", help="Deliberately redo from this stage instead of the failed one."
    ),
    with_designer: bool = typer.Option(
        False, "--with-designer",
        help="Keep the Designer stage enabled (pass again if the original run used it).",
    ),
    with_tester: bool = typer.Option(
        False, "--with-tester",
        help="Keep the Tester stage enabled (pass again if the original run used it).",
    ),
    with_publisher: bool = typer.Option(
        False, "--with-publisher",
        help="Keep the Publisher stage enabled (pass again if the original run used it).",
    ),
) -> None:
    """Continue a failed run from its failed stage."""
    project_dir = Path.cwd()
    manager = RunManager(project_dir)
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
    shared.check_same_pipeline(state, resolved, "resume")

    render.console.print(f"[bold]resuming:[/bold] {state.request}")
    engine, manager = shared.build_engine(project_dir, loaded, transport)
    state = shared.drive(
        lambda: engine.resume(state, resolved, from_stage=from_stage), manager,
        run_id_hint=run_id,
    )
    shared.finish(state, manager)
