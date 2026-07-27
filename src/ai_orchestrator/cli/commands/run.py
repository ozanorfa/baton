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
from ai_orchestrator.core.reporter import save_report
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
    if status.returncode != 0:
        # Not a git repo: diff capture and silent-failure detection are off (ADR-013).
        render.console.print(
            "[yellow]⚠ not a git repository — diff capture and the no-change safety "
            "check are disabled. Run `git init` first to enable them.[/yellow]"
        )
    elif status.stdout.strip():
        render.console.print(
            "[yellow]⚠ git working tree is not clean — the coder's changes will mix "
            "with yours. Consider committing or stashing first.[/yellow]"
        )


def run(
    request: str = typer.Argument(..., help="What you want done."),
    with_designer: bool = typer.Option(
        False, "--with-designer", help="Enable the optional Designer stage for this run."
    ),
    with_tester: bool = typer.Option(
        False, "--with-tester",
        help="Enable the optional Tester stage (runs the project's tests, zero-LLM — ADR-024).",
    ),
    with_publisher: bool = typer.Option(
        False, "--with-publisher",
        help="Enable the optional Publisher stage (drafts commit message + PR description; "
        "never runs git itself — ADR-014).",
    ),
    fix_loop: bool = typer.Option(
        False, "--fix-loop",
        help="On a NEEDS WORK verdict, run one automatic fix pass (re-run the Coder with "
        "the review findings, then re-review) — ADR-023.",
    ),
    health: bool = typer.Option(
        False, "--health",
        help="Inject repowise code-health hotspots into every stage prompt (needs the "
        "`repowise` binary; adds ~4s, writes a temporary .repowise/ index) — ADR-025.",
    ),
) -> None:
    """Run the configured pipeline on a request."""
    project_dir = Path.cwd()
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
    state = engine.execute(request, resolved)

    report = save_report(state, manager)
    render.render_run_summary(state, manager.run_dir(state.run_id), report)

    # fix-loop (ADR-023): one automatic fix pass on a blocking verdict. Exactly
    # one — the second verdict is never re-checked, so it can't loop.
    if (
        loaded.config.pipeline.fix_loop
        and state.status is RunStatus.SUCCEEDED
        and report.verdict == "NEEDS WORK"
    ):
        review = manager.load_artifact(state, "review.md")
        correction = (
            "The reviewer returned NEEDS WORK (blocking findings). Address them, "
            "then stop:\n\n" + review
        )
        render.console.print(
            "[yellow]⟳ reviewer flagged blockers — running one fix pass (--fix-loop)…[/yellow]"
        )
        state = engine.revise(state, resolved, correction)
        report = save_report(state, manager)
        render.render_run_summary(state, manager.run_dir(state.run_id), report)

    if state.status is not RunStatus.SUCCEEDED:
        raise typer.Exit(code=1)
