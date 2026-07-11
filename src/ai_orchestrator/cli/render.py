"""All Rich terminal output lives here; the core stays terminal-agnostic."""

from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.table import Table

from ai_orchestrator.config.loader import LoadedConfig
from ai_orchestrator.core.models import AgentResult, Health, RunState, StageStatus

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


def render_usage_line(result: AgentResult) -> None:
    """Measured values only; '—' where the provider reports nothing (risk R2)."""
    usage = result.usage
    parts = []
    if usage is not None and (usage.input_tokens or usage.output_tokens):
        parts.append(f"tokens in/out: {usage.input_tokens or '—'}/{usage.output_tokens or '—'}")
    if usage is not None and usage.cost_usd is not None:
        parts.append(f"cost: ${usage.cost_usd:.4f}")
    if result.session_id:
        parts.append(f"session: {result.session_id}")
    if parts:
        console.print("  ".join(parts), style="dim")


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
            totals.append(f"measured cost ${report.total_cost_usd:.2f}")
        if totals:
            console.print("totals: " + " · ".join(totals), style="dim")

    if state.status.value == "failed":
        failed_idx, failed = next(
            (i, s) for i, s in enumerate(state.stages, start=1)
            if s.status is StageStatus.FAILED
        )
        error_console.print(f"\nstage {failed.name!r} failed: {failed.error}")
        stderr_file = run_dir / "logs" / f"{failed_idx:02d}-{failed.name}.stderr"
        if stderr_file.is_file() and stderr_file.read_text().strip():
            console.print(f"raw stderr:  {stderr_file}")
        console.print(f"run detail:  {run_dir}")
        console.print(
            "next steps:  [bold]ai doctor[/bold] (provider health) · inspect the files above"
        )
    else:
        if report is not None and report.verdict:
            color = "green" if report.verdict.startswith("APPROVE") else "yellow"
            console.print(f"reviewer verdict: [{color}]{report.verdict}[/{color}]")
        console.print(f"[green]run succeeded[/green] · artifacts: {run_dir / 'artifacts'}")
        console.print(f"[dim]report: {run_dir / 'report.json'}[/dim]")


@dataclass
class DoctorRow:
    provider: str
    command: str
    roles: list[str]
    health: Health


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
        else:
            status = f"[red]✗ {row.health.detail or 'unavailable'}[/red]"
        table.add_row(
            row.provider,
            row.command,
            row.health.version or "—",
            ", ".join(row.roles) or "—",
            status,
        )
    console.print(table)
