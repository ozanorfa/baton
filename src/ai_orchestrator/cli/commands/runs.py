"""`batonai runs` — run history of the current project."""

import json
from pathlib import Path

import typer

from ai_orchestrator.cli import render
from ai_orchestrator.core.reporter import SEVERITIES, build_report, diff_stats, review_findings
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



def _measure(manager: RunManager, run_id: str) -> dict:
    """One run as numbers (ADR-036): what it cost, what it changed, what the
    Reviewer found. Everything is read from the run directory; nothing is
    estimated — a missing artifact is reported as missing, not as zero."""
    state = manager.load_run(run_id)
    report = build_report(state, manager)
    artifacts = manager.artifacts_dir(run_id)
    patch_file = artifacts / "diff.patch"
    review_file = artifacts / "review.md"
    files = added = removed = None
    if patch_file.is_file():
        files, added, removed = diff_stats(patch_file.read_text(encoding="utf-8"))
    findings = (
        review_findings(review_file.read_text(encoding="utf-8")) if review_file.is_file() else None
    )
    stages = [s for s in state.stages if s.status.value in ("succeeded", "failed")]
    return {
        "run_id": run_id,
        "request": state.request.splitlines()[0][:80],
        "status": state.status.value,
        "stages": [s.name for s in stages],
        "wall_s": round(report.wall_duration_s) if report.wall_duration_s is not None else None,
        "input_tokens": report.total_input_tokens,
        "output_tokens": report.total_output_tokens,
        "cost_usd": report.total_cost_usd,
        "verdict": report.verdict,
        "findings": findings,
        "files_changed": files,
        "lines_added": added,
        "lines_removed": removed,
    }


def _cell(value) -> str:
    return "—" if value is None else str(value)


@runs_app.command("export")
def export_runs(
    run_ids: list[str] | None = typer.Argument(  # noqa: B008 — Typer idiom
        None, help="Run ids (default: every run)."
    ),
    fmt: str = typer.Option("md", "--format", help="md (a Markdown table) or json."),
) -> None:
    """Measurements per run, ready to paste into an evaluation table (ADR-036)."""
    manager = RunManager(Path.cwd())
    ids = run_ids or manager.list_run_ids()
    if not ids:
        render.console.print("no runs yet — try: batonai \"<request>\"")
        return
    try:
        rows = [_measure(manager, run_id) for run_id in ids]
    except FileNotFoundError as exc:
        render.render_error(str(exc))
        raise typer.Exit(code=2) from exc

    if fmt == "json":
        typer.echo(json.dumps(rows, indent=2))
        return
    if fmt != "md":
        render.render_error(f"unknown format {fmt!r}; use md or json")
        raise typer.Exit(code=2)

    sev = " / ".join(SEVERITIES)
    typer.echo(
        "| run | request | status | wall s | tokens in/out | cost $ | verdict | "
        f"findings ({sev}) | files | +/- |"
    )
    typer.echo("|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        tokens = (
            f"{r['input_tokens']:,}/{r['output_tokens'] or 0:,}"
            if r["input_tokens"] is not None else "—"
        )
        cost = f"{r['cost_usd']:.2f}" if r["cost_usd"] is not None else "—"
        found = (
            " / ".join(str(r["findings"][s]) for s in SEVERITIES) if r["findings"] else "—"
        )
        plus_minus = (
            f"+{r['lines_added']}/-{r['lines_removed']}" if r["files_changed"] is not None else "—"
        )
        typer.echo(
            f"| {r['run_id']} | {r['request']} | {r['status']} | {_cell(r['wall_s'])} | "
            f"{tokens} | {cost} | {_cell(r['verdict'])} | {found} | "
            f"{_cell(r['files_changed'])} | {plus_minus} |"
        )
