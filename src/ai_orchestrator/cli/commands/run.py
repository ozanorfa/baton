"""`batonai run "<request>"` — the pipeline. Reachable as bare `batonai "<request>"`
via the argv rewrite in app.main()."""

import subprocess
from pathlib import Path

import typer

from ai_orchestrator.cli import render
from ai_orchestrator.cli.commands import _shared as shared
from ai_orchestrator.core.models import RunStatus
from ai_orchestrator.core.reporter import save_report
from ai_orchestrator.transport.headless import HeadlessTransport


def _warn_if_dirty_git_tree(project_dir: Path) -> None:
    """ADR-007: a run should start from a clean tree so its diff is unambiguous."""
    try:
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=project_dir, capture_output=True, text=True, timeout=10, shell=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return
    if status.returncode != 0:
        # Not a git repo: diff capture and silent-failure detection are off (ADR-013).
        render.console.print(
            "[yellow]⚠ not a git repository — diff capture and the no-change safety "
            "check are disabled. Run `git init` first to enable them.[/yellow]"
        )
    elif not _has_commits(project_dir):
        # ADR-029: reported, never fixed — baton creates no commits outside
        # `batonai publish` (ADR-020), so it names the state and the remedy.
        render.console.print(
            "[yellow]⚠ this repository has no commits yet — there is no baseline to "
            "diff against, so the whole project will read as the coder's work.\n"
            "  fix: git add -A && git commit -m \"initial commit\"[/yellow]"
        )
    elif status.stdout.strip():
        render.console.print(
            "[yellow]⚠ git working tree is not clean — the coder's changes will mix "
            "with yours in the reviewer's diff. Consider committing or stashing first.[/yellow]"
        )


def _has_commits(project_dir: Path) -> bool:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"],
            cwd=project_dir, capture_output=True, text=True, timeout=10, shell=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return True  # can't tell → don't cry wolf
    return proc.returncode == 0


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
    loaded = shared.load_config_or_exit(
        project_dir,
        shared.stage_overrides(
            with_designer=with_designer, with_tester=with_tester,
            with_publisher=with_publisher, fix_loop=fix_loop, health=health,
        ),
    )
    transport = HeadlessTransport()
    resolved = shared.preflight_or_exit(loaded, transport)

    _warn_if_dirty_git_tree(project_dir)
    render.render_run_header(request, resolved)

    engine, manager = shared.build_engine(project_dir, loaded, transport)
    state = shared.drive(lambda: engine.execute(request, resolved), manager)

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
        state = shared.drive(
            lambda: engine.revise(state, resolved, correction), manager,
            run_id_hint=state.run_id,
        )
        report = save_report(state, manager)
        render.render_run_summary(state, manager.run_dir(state.run_id), report)

    if state.status is not RunStatus.SUCCEEDED:
        raise typer.Exit(code=shared.EXIT_STAGE_FAILED)
