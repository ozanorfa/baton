"""All Rich terminal output lives here; the core stays terminal-agnostic."""

from dataclasses import dataclass

from rich.console import Console
from rich.table import Table

from ai_orchestrator.config.loader import LoadedConfig
from ai_orchestrator.core.models import Health

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
