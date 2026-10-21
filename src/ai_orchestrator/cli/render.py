"""All Rich terminal output lives here; the core stays terminal-agnostic."""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ai_orchestrator.config.loader import LoadedConfig
from ai_orchestrator.core.models import (
    AgentResult,
    Health,
    RunState,
    RunStatus,
    StageStatus,
    utcnow,
)

console = Console()
error_console = Console(stderr=True, style="bold red")


def _flatten(data: dict, prefix: str = "") -> list[tuple[str, object]]:
    leaves: list[tuple[str, object]] = []
    for key, value in data.items():
        dotted = f"{prefix}{key}"
        if isinstance(value, dict) and value:
            leaves.extend(_flatten(value, f"{dotted}."))
        else:
            leaves.append((dotted, value))
    return leaves


def render_config(loaded: LoadedConfig) -> None:
    table = Table(title="Effective configuration", header_style="bold")
    table.add_column("setting")
    table.add_column("value")
    table.add_column("source", style="dim")

    for dotted, value in _flatten(loaded.config.model_dump(mode="json")):
        rendered = "—" if value is None else str(value)
        table.add_row(dotted, rendered, loaded.source_of(dotted))

    console.print(table)
    if loaded.files_read:
        console.print("files read:", ", ".join(str(p) for p in loaded.files_read), style="dim")
    else:
        console.print("files read: none (built-in defaults only)", style="dim")


def render_error(message: str) -> None:
    error_console.print(message)


COST_NOTE = (
    "cost = provider-reported API-equivalent value; on subscription plans "
    "(Claude Pro/Max, ChatGPT) it consumes plan quota — no per-run charge"
)


def render_usage_line(result: AgentResult) -> None:
    """Measured values only; '—' where the provider reports nothing (risk R2)."""
    usage = result.usage
    parts = []
    if usage is not None and (usage.input_tokens or usage.output_tokens):
        parts.append(f"tokens in/out: {usage.input_tokens or '—'}/{usage.output_tokens or '—'}")
    if usage is not None and usage.cost_usd is not None:
        parts.append(f"cost: ${usage.cost_usd:.4f}*")
    if result.session_id:
        parts.append(f"session: {result.session_id}")
    if parts:
        console.print("  ".join(parts), style="dim")
    if usage is not None and usage.cost_usd is not None:
        console.print(f"* {COST_NOTE}", style="dim")


def render_commit_draft(message: str, source: str) -> None:
    """Show the commit message that `batonai publish` would use, in a panel.

    The source goes on its own line: as a panel subtitle it was clipped to the
    panel's width, so a one-line message hid which run or provider drafted it.
    """
    console.print(Panel(message.strip(), title="commit message", expand=False))
    console.print(f"[dim]source: {source}[/dim]")


def render_publish_plan(changed: list[str], will_push: bool) -> None:
    """Show what a publish would stage/commit before asking for confirmation."""
    if not changed:
        console.print("[yellow]nothing to commit — working tree is clean.[/yellow]")
        return
    console.print(f"[bold]will commit {len(changed)} change(s):[/bold]")
    for line in changed:
        console.print(f"  {line}", style="dim")
    console.print(
        "[dim]→ git add -A · git commit"
        + (" · git push" if will_push else " (no push)")
        + "[/dim]"
    )


def render_run_header(request: str, resolved) -> None:
    stages = " → ".join(
        f"{r.spec.name}[{r.provider_name}]" + ("" if r.enabled else " (off)") for r in resolved
    )
    console.print(f"[bold]run:[/bold] {request}")
    console.print(f"[dim]{stages}[/dim]")


class ProgressRenderer:
    """Live per-stage progress from the engine's event stream: an animated
    spinner while a provider works, a result line when it finishes."""

    def __init__(self) -> None:
        self._status = None

    def _stop_spinner(self) -> None:
        if self._status is not None:
            self._status.stop()
            self._status = None

    def handle(self, record: dict) -> None:
        event, stage = record.get("event"), record.get("stage", "")
        if event == "stage_started":
            self._status = console.status(
                f"[bold]{stage}[/bold] ({record.get('provider')}) working…", spinner="dots"
            )
            self._status.start()
        elif event == "stage_progress":
            # ADR-030: replace the spinner's text rather than printing a line per
            # note — a ten-minute stage would otherwise bury the run in scrollback.
            if self._status is not None:
                note = record.get("note", "")
                self._status.update(f"[bold]{stage}[/bold] [dim]{note}[/dim]")
        elif event == "stage_succeeded":
            self._stop_spinner()
            duration = record.get("duration_s")
            suffix = f" in {duration:.0f}s" if isinstance(duration, int | float) else ""
            console.print(f"  [green]✓ {stage}[/green] → {record.get('artifact')}{suffix}")
        elif event == "stage_skipped":
            self._stop_spinner()
            console.print(f"  [dim]○ {stage} skipped ({record.get('reason')})[/dim]")
        elif event == "stage_failed":
            self._stop_spinner()
            console.print(f"  [red]✗ {stage} FAILED[/red]")
        elif event == "run_finished":
            self._stop_spinner()


def _format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}m {secs:02d}s" if minutes else f"{secs}s"


def _tokens_cell(stage) -> str:
    usage = stage.usage
    if not usage or (usage.input_tokens is None and usage.output_tokens is None):
        return "—"
    left = f"{usage.input_tokens:,}" if usage.input_tokens is not None else "—"
    right = f"{usage.output_tokens:,}" if usage.output_tokens is not None else "—"
    return f"{left}/{right}"


def render_run_summary(state: RunState, run_dir: Path, report=None) -> None:
    table = Table(title=f"run {state.run_id}", header_style="bold")
    for column in ("stage", "provider", "duration", "tokens in/out", "status"):
        table.add_column(column)

    for stage in state.stages:
        style = {
            StageStatus.SUCCEEDED: "[green]✓[/green]",
            StageStatus.FAILED: "[red]✗[/red]",
            StageStatus.SKIPPED: "[dim]○ skipped[/dim]",
            StageStatus.PENDING: "[dim]· pending[/dim]",
            StageStatus.RUNNING: "[yellow]… running[/yellow]",
        }.get(stage.status, str(stage.status))
        table.add_row(
            stage.name,
            stage.provider or "—",
            _format_duration(stage.duration_s),
            _tokens_cell(stage),
            style,
        )
    console.print(table)

    if report is not None:
        totals = []
        if report.total_input_tokens is not None:
            totals.append(
                f"tokens {report.total_input_tokens:,}/{report.total_output_tokens or 0:,}"
            )
        if report.total_cost_usd is not None:
            totals.append(f"measured cost ${report.total_cost_usd:.2f}*")
        if totals:
            console.print("totals: " + " · ".join(totals), style="dim")
        if report.total_cost_usd is not None:
            console.print(f"* {COST_NOTE}", style="dim")

    if state.status is RunStatus.FAILED:
        failed_idx, failed = next(
            (i, s) for i, s in enumerate(state.stages, start=1)
            if s.status is StageStatus.FAILED
        )
        error_console.print(f"\nstage {failed.name!r} failed: {failed.error}")
        stderr_file = run_dir / "logs" / f"{failed_idx:02d}-{failed.name}.stderr"
        if stderr_file.is_file() and stderr_file.read_text(encoding="utf-8").strip():
            console.print(f"raw stderr:  {stderr_file}")
        console.print(f"run detail:  {run_dir}")
        console.print(
            f"next steps:  [bold]batonai resume {state.run_id}[/bold] "
            "(retry from the failed stage) · [bold]batonai doctor[/bold] (provider health)"
        )
    elif state.status is RunStatus.RUNNING:
        # ADR-034: a run.json still saying "running" means either another
        # baton process is mid-run, or one died without the chance to record
        # the failure. It is NOT a success and must never render as one.
        active = next((s.name for s in state.stages if s.status is StageStatus.RUNNING), None)
        where = f" (stage {active!r})" if active else ""
        console.print(
            f"[yellow]run not finished{where}[/yellow] — still in progress in another "
            "process, or the process died before recording a result."
        )
        console.print(f"run detail:  {run_dir}")
        console.print(
            f"next steps:  if nothing is running, [bold]batonai resume {state.run_id}[/bold] "
            "continues from the unfinished stage"
        )
    else:
        if report is not None and report.verdict:
            color = "green" if report.verdict.startswith("APPROVE") else "yellow"
            console.print(f"reviewer verdict: [{color}]{report.verdict}[/{color}]")
        console.print(f"[green]run succeeded[/green] · artifacts: {run_dir / 'artifacts'}")
        console.print(f"[dim]report: {run_dir / 'report.json'}[/dim]")


_STATUS_GLYPH = {
    StageStatus.SUCCEEDED: "✓",
    StageStatus.FAILED: "✗",
    StageStatus.SKIPPED: "○",
    StageStatus.PENDING: "·",
    StageStatus.RUNNING: "…",
}


def render_runs_list(rows) -> None:
    """rows: list of (RunState, Report) tuples, oldest first."""
    table = Table(title="runs", header_style="bold")
    for column in ("run id", "status", "stages", "cost", "verdict", "request"):
        table.add_column(column)
    for state, report in rows:
        glyphs = "".join(_STATUS_GLYPH.get(s.status, "?") for s in state.stages)
        status = {
            "succeeded": "[green]succeeded[/green]",
            "failed": "[red]failed[/red]",
            "running": "[yellow]unfinished[/yellow]",
        }.get(state.status.value, state.status.value)
        cost = f"${report.total_cost_usd:.2f}" if report.total_cost_usd is not None else "—"
        request = state.request if len(state.request) <= 48 else state.request[:45] + "…"
        table.add_row(state.run_id, status, glyphs, cost, report.verdict or "—", request)
    console.print(table)
    if any(report.total_cost_usd is not None for _, report in rows):
        console.print(COST_NOTE, style="dim")


@dataclass
class DoctorRow:
    provider: str
    command: str
    roles: list[str]
    health: Health
    required: bool = True  # bound to an enabled stage; optional ones never fail doctor


def render_doctor(rows: list[DoctorRow]) -> None:
    table = Table(title="Provider health", header_style="bold")
    table.add_column("provider")
    table.add_column("command")
    table.add_column("version")
    table.add_column("used by", style="dim")
    table.add_column("status")

    for row in rows:
        if row.health.ok:
            status = "[green]✓ healthy[/green]"
        elif row.required:
            status = f"[red]✗ {row.health.detail or 'unavailable'}[/red]"
        else:
            status = f"[dim]○ optional — {row.health.detail or 'unavailable'}[/dim]"
        table.add_row(
            row.provider,
            row.command,
            row.health.version or "—",
            ", ".join(row.roles) or "—",
            status,
        )
    console.print(table)
    if any(not r.health.ok and not r.required for r in rows):
        console.print(
            "[dim]○ optional = no enabled stage uses it; install it only if you turn that "
            "stage on (--with-designer / --with-publisher).[/dim]"
        )


# ── Interactive front door (ADR-026) ────────────────────────────────────────

def render_banner() -> None:
    console.print("\n[bold]baton[/bold] — AI coding pipeline")
    console.print("[dim]planner → coder → reviewer, across Codex / Claude Code[/dim]\n")


def _relative_age(created: datetime, now: datetime | None = None) -> str:
    now = now or utcnow()
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    seconds = max(0, int((now - created).total_seconds()))
    if seconds < 90:
        return "just now"
    if seconds < 5400:
        return f"{seconds // 60}m ago"
    if seconds < 172800:
        return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"


def render_scan(state) -> None:
    """The 'here is what I found' report the wizard opens with (ADR-026)."""
    def row(mark: str, label: str, detail: str) -> None:
        console.print(f"  {mark} [bold]{label:<10}[/bold] {detail}")

    ok, warn = "[green]✓[/green]", "[yellow]⚠[/yellow]"

    if state.issues:
        for issue in state.issues:
            row("[red]✗[/red]", "providers",
                f"[red]{issue.provider} — {issue.detail}[/red] "
                f"[dim](needed by: {', '.join(issue.roles)})[/dim]")
    else:
        row(ok, "providers", "all healthy")

    if state.is_empty:
        row(ok, "project", "empty folder — a new project")
    else:
        stack = "; ".join(state.stack) if state.stack else str(state.mode)
        row(ok, "project", stack)

    if not state.is_git:
        row(warn, "git", "not a repository — diff capture and the no-change "
                         "safety check are off")
    elif not state.has_commits:
        # ADR-029: distinct from "dirty" — with no HEAD there is no baseline, so
        # every file reads as a change and the Coder's diff becomes the project.
        row(warn, "git", "repository has no commits yet — with no baseline, every "
                         "file counts as a change and the diff will be the whole "
                         "project")
        console.print("       [dim]fix: git add -A && git commit -m \"initial commit\""
                      "  (baton never commits for you)[/dim]")
    elif state.git_dirty:
        row(warn, "git", "uncommitted changes present")
    else:
        row(ok, "git", "clean")

    if state.has_ai_dir:
        if state.last_run is not None:
            last = state.last_run
            verdict = f" · {last.verdict}" if last.verdict else ""
            row(ok, "baton", f"ready · last run {_relative_age(last.created_at)}"
                             f'{verdict} · "{last.request[:48]}"')
        else:
            row(ok, "baton", "ready · no runs yet")
    else:
        row(warn, "baton", "not set up in this folder yet")

    if state.health:
        worst = [ln for ln in state.health.splitlines() if ln.startswith("- `")][:3]
        row(ok, "health", "code hotspots found [dim](repowise)[/dim]")
        for line in worst:
            console.print(f"       [dim]{line.lstrip('- ').replace('`', '')}[/dim]")
    console.print()
