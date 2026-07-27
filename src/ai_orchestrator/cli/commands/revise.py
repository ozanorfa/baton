"""`ai revise "<correction>"` — iterate on the last run without starting over (ADR-019).

Re-runs a completed run from the Coder (by default), carrying the prior run's
provider sessions forward so the Coder resumes its own session and treats the
correction as the next turn. Keeps the same run-id and reuses on-disk artifacts.
The correction is injected into the run's request so every re-run stage sees it.
"""

from pathlib import Path

import typer

from ai_orchestrator.cli import render
from ai_orchestrator.config.loader import ConfigError, load_config
from ai_orchestrator.context.manager import ContextManager
from ai_orchestrator.core.engine import PipelineEngine, ResumeError
from ai_orchestrator.core.models import RunStatus
from ai_orchestrator.core.reporter import save_report
from ai_orchestrator.core.routing import RoutingEngine, RoutingError, build_stage_specs
from ai_orchestrator.core.run_manager import RunManager
from ai_orchestrator.providers import load_all
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

    if run_id is None:
        run_id = manager.latest_run_id()
        if run_id is None:
            render.render_error("no runs to revise yet — start one with `ai \"<request>\"`.")
            raise typer.Exit(code=2)

    try:
        state = manager.load_run(run_id)
    except FileNotFoundError as exc:
        render.render_error(str(exc))
        raise typer.Exit(code=2) from exc

    overrides: dict[str, object] = {}
    if with_designer:
        overrides["roles.designer.enabled"] = True
    if with_tester:
        overrides["roles.tester.enabled"] = True
    if with_publisher:
        overrides["roles.publisher.enabled"] = True
    try:
        loaded = load_config(project_dir, overrides=overrides)
    except ConfigError as exc:
        render.render_error(str(exc))
        raise typer.Exit(code=2) from exc

    transport = HeadlessTransport()
    try:
        specs = build_stage_specs(loaded.config)
        resolved = RoutingEngine(loaded.config, load_all()).resolve(specs, transport)
    except RoutingError as exc:
        render.render_error(f"preflight failed: {exc}")
        raise typer.Exit(code=2) from exc

    config_names = [s.name for s in specs]
    run_names = [s.name for s in state.stages]
    if config_names != run_names:
        render.render_error(
            f"cannot revise: the pipeline configuration changed since run {run_id}.\n"
            f"  run was:    {run_names}\n"
            f"  config now: {config_names}\n"
            "Start a fresh run instead."
        )
        raise typer.Exit(code=2)

    render.console.print(f"[bold]revising[/bold] {run_id}: {correction}")
    context = ContextManager(
        project_dir,
        loaded.config.context.project_profile,
        include_health=loaded.config.context.health,
    )
    progress = render.ProgressRenderer()
    engine = PipelineEngine(
        manager, transport, prompt_builder=context.build, event_sink=progress.handle,
        session_chaining=loaded.config.pipeline.session_chaining,
    )
    try:
        state = engine.revise(state, resolved, correction, from_stage=from_stage)
    except ResumeError as exc:
        render.render_error(str(exc))
        raise typer.Exit(code=2) from exc

    report = save_report(state, manager)
    render.render_run_summary(state, manager.run_dir(state.run_id), report)
    if state.status is not RunStatus.SUCCEEDED:
        raise typer.Exit(code=1)
