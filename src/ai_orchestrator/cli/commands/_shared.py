"""What `run`, `resume` and `revise` have in common (ADR-034).

The three pipeline commands used to carry three copies of the same prelude
(flag → override mapping, config load, routing preflight, engine wiring) and
three copies of the same epilogue (report, summary, exit code). The copies had
already drifted in small ways; this module is the single version.

It also owns the one behaviour none of them had: a Ctrl-C *during* a stage
ends with the run summary and exit 130, so the user sees which stage was cut
short and how to resume it — instead of Click's bare "Aborted!" or, inside the
wizard, a message claiming nothing was changed.
"""

from collections.abc import Callable
from pathlib import Path

import typer

from ai_orchestrator.cli import render
from ai_orchestrator.config.loader import ConfigError, LoadedConfig, load_config
from ai_orchestrator.context.manager import ContextManager
from ai_orchestrator.core.engine import PipelineEngine, ResumeError
from ai_orchestrator.core.models import RunState, RunStatus
from ai_orchestrator.core.reporter import save_report
from ai_orchestrator.core.routing import (
    ResolvedStage,
    RoutingEngine,
    RoutingError,
    build_stage_specs,
)
from ai_orchestrator.core.run_manager import RunManager
from ai_orchestrator.providers import load_all
from ai_orchestrator.transport.headless import HeadlessTransport

EXIT_STAGE_FAILED = 1
EXIT_USAGE = 2
EXIT_INTERRUPTED = 130  # the conventional SIGINT exit code


def stage_overrides(
    *, with_designer: bool = False, with_tester: bool = False, with_publisher: bool = False,
    fix_loop: bool = False, health: bool = False,
) -> dict[str, object]:
    """Map the per-run flags onto config overrides (highest-precedence layer)."""
    overrides: dict[str, object] = {}
    if with_designer:
        overrides["roles.designer.enabled"] = True
    if with_tester:
        overrides["roles.tester.enabled"] = True
    if with_publisher:
        overrides["roles.publisher.enabled"] = True
    if fix_loop:
        overrides["pipeline.fix_loop"] = True
    if health:
        overrides["context.health"] = True
    return overrides


def load_config_or_exit(project_dir: Path, overrides: dict[str, object]) -> LoadedConfig:
    try:
        return load_config(project_dir, overrides=overrides)
    except ConfigError as exc:
        render.render_error(str(exc))
        raise typer.Exit(code=EXIT_USAGE) from exc


def preflight_or_exit(
    loaded: LoadedConfig, transport: HeadlessTransport
) -> list[ResolvedStage]:
    """Resolve every stage and health-check every provider before spending anything."""
    try:
        specs = build_stage_specs(loaded.config)
        return RoutingEngine(loaded.config, load_all()).resolve(specs, transport)
    except RoutingError as exc:
        render.render_error(f"preflight failed: {exc}")
        raise typer.Exit(code=EXIT_USAGE) from exc


def check_same_pipeline(state: RunState, resolved: list[ResolvedStage], verb: str) -> None:
    """`resume`/`revise` need the run's stage list to match today's config."""
    config_names = [r.spec.name for r in resolved]
    run_names = [s.name for s in state.stages]
    if config_names != run_names:
        render.render_error(
            f"cannot {verb}: the pipeline configuration changed since run {state.run_id}.\n"
            f"  run was:    {run_names}\n"
            f"  config now: {config_names}\n"
            "Start a fresh run instead."
        )
        raise typer.Exit(code=EXIT_USAGE)


def build_engine(
    project_dir: Path, loaded: LoadedConfig, transport: HeadlessTransport
) -> tuple[PipelineEngine, RunManager]:
    manager = RunManager(project_dir)
    context = ContextManager(
        project_dir,
        loaded.config.context.project_profile,
        include_health=loaded.config.context.health,
    )
    progress = render.ProgressRenderer()
    engine = PipelineEngine(
        manager, transport,
        prompt_builder=context.build,
        event_sink=progress.handle,
        session_chaining=loaded.config.pipeline.session_chaining,
    )
    return engine, manager


def drive(
    action: Callable[[], RunState], manager: RunManager, *, run_id_hint: str | None = None
) -> RunState:
    """Execute one engine action with the shared failure handling.

    - `ResumeError` is a usage error (exit 2) with the engine's message.
    - Ctrl-C: the engine has already recorded the interrupted stage as FAILED
      (T34); here the summary is rendered so the user sees it, then exit 130.
    """
    try:
        return action()
    except ResumeError as exc:
        render.render_error(str(exc))
        raise typer.Exit(code=EXIT_USAGE) from exc
    except KeyboardInterrupt as exc:
        run_id = run_id_hint or manager.latest_run_id()
        render.console.print()
        if run_id is not None:
            try:
                state = manager.load_run(run_id)
            except (FileNotFoundError, OSError, ValueError):
                state = None
            if state is not None:
                save_report(state, manager)
                render.render_run_summary(state, manager.run_dir(run_id), None)
        render.console.print(
            "[yellow]interrupted — the run above was stopped mid-stage; files the coder "
            "already wrote are still in your working tree.[/yellow]"
        )
        raise typer.Exit(code=EXIT_INTERRUPTED) from exc


def finish(state: RunState, manager: RunManager) -> None:
    """Report + summary; exit 1 unless the run succeeded."""
    report = save_report(state, manager)
    render.render_run_summary(state, manager.run_dir(state.run_id), report)
    if state.status is not RunStatus.SUCCEEDED:
        raise typer.Exit(code=EXIT_STAGE_FAILED)
