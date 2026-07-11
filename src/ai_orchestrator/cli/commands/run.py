"""`ai run "<request>"` — the pipeline. Reachable as bare `ai "<request>"`
via the argv rewrite in app.main()."""

import subprocess
from pathlib import Path

import typer

from ai_orchestrator.cli import render
from ai_orchestrator.config.loader import ConfigError, load_config
from ai_orchestrator.context.manager import ContextManager
from ai_orchestrator.core.engine import PipelineEngine
from ai_orchestrator.core.models import RunStatus
from ai_orchestrator.core.routing import RoutingEngine, RoutingError, build_stage_specs
from ai_orchestrator.core.run_manager import RunManager
from ai_orchestrator.providers import load_all
from ai_orchestrator.transport.headless import HeadlessTransport


def _warn_if_dirty_git_tree(project_dir: Path) -> None:
    """ADR-007: a run should start from a clean tree so its diff is unambiguous."""
    try:
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=project_dir, capture_output=True, text=True, timeout=10, shell=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return
    if status.returncode == 0 and status.stdout.strip():
        render.console.print(
            "[yellow]⚠ git working tree is not clean — the coder's changes will mix "
            "with yours. Consider committing or stashing first.[/yellow]"
        )


def run(
    request: str = typer.Argument(..., help="What you want done."),
    with_designer: bool = typer.Option(
        False, "--with-designer", help="Enable the optional Designer stage for this run."
    ),
) -> None:
    """Run the configured pipeline on a request."""
    project_dir = Path.cwd()
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

    _warn_if_dirty_git_tree(project_dir)
    render.render_run_header(request, resolved)

    manager = RunManager(project_dir)
    context = ContextManager(project_dir, loaded.config.context.project_profile)
    engine = PipelineEngine(
        manager, transport,
        prompt_builder=context.build,
        event_sink=render.render_progress_event,
    )
    state = engine.execute(request, resolved)

    render.render_run_summary(state, manager.run_dir(state.run_id))
    if state.status is not RunStatus.SUCCEEDED:
        raise typer.Exit(code=1)
