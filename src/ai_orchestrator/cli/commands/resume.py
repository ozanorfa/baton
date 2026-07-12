"""`ai resume <run-id>` — continue a failed run from its failed stage,
reusing every artifact that already succeeded (T33)."""

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


def resume(
    run_id: str = typer.Argument(..., help="Run id (see `ai runs list`)."),
    from_stage: str = typer.Option(
        None, "--from", help="Deliberately redo from this stage instead of the failed one."
    ),
    with_designer: bool = typer.Option(
        False, "--with-designer",
        help="Keep the Designer stage enabled (pass again if the original run used it).",
    ),
) -> None:
    """Continue a failed run from its failed stage."""
    project_dir = Path.cwd()
    manager = RunManager(project_dir)
    try:
        state = manager.load_run(run_id)
    except FileNotFoundError as exc:
        render.render_error(str(exc))
        raise typer.Exit(code=2) from exc

    overrides: dict[str, object] = {}
    if with_designer:
        overrides["roles.designer.enabled"] = True
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
            f"cannot resume: the pipeline configuration changed since run {run_id}.\n"
            f"  run was:    {run_names}\n"
            f"  config now: {config_names}\n"
            "Start a fresh run instead."
        )
        raise typer.Exit(code=2)

    render.console.print(f"[bold]resuming:[/bold] {state.request}")
    context = ContextManager(project_dir, loaded.config.context.project_profile)
    progress = render.ProgressRenderer()
    engine = PipelineEngine(
        manager, transport, prompt_builder=context.build, event_sink=progress.handle
    )
    try:
        state = engine.resume(state, resolved, from_stage=from_stage)
    except ResumeError as exc:
        render.render_error(str(exc))
        raise typer.Exit(code=2) from exc

    report = save_report(state, manager)
    render.render_run_summary(state, manager.run_dir(state.run_id), report)
    if state.status is not RunStatus.SUCCEEDED:
        raise typer.Exit(code=1)
