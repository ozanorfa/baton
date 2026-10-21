"""`batonai setup` — change which AI does which job, and on which model.

ADR-032. The role→provider map (ADR-016) and the model (ADR-031) are the two
decisions that most affect cost, speed and quality, and both were previously
fixed at `init` time or inherited invisibly from each CLI. This command makes
them revisable at any point without hand-editing YAML.

It edits `.ai/config.yaml` in place. That file is data, not prose, so it is
re-serialised from the parsed document: any comments in it are lost, which the
command says out loud before writing.
"""

from pathlib import Path

import typer
import yaml

from ai_orchestrator.cli import model_catalog, render
from ai_orchestrator.config.loader import ConfigError, load_config
from ai_orchestrator.providers import load_all

CONFIG_RELPATH = Path(".ai") / "config.yaml"

# Roles whose provider is a real choice. The zero-LLM roles are excluded: the
# tester runs your test command and the deterministic publisher floor is a
# `git diff` formatter — neither has a model to pick.
CHOOSABLE_ROLES = ("planner", "designer", "coder", "reviewer", "publisher")


def _load_document(project_dir: Path) -> dict:
    path = project_dir / CONFIG_RELPATH
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8", errors="replace"))
    except yaml.YAMLError as exc:
        render.render_error(f"{path}: not valid YAML — {exc}")
        raise typer.Exit(code=2) from exc
    return data if isinstance(data, dict) else {}


def _write_document(project_dir: Path, document: dict) -> Path:
    path = project_dir / CONFIG_RELPATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(document, sort_keys=False, default_flow_style=False), encoding="utf-8"
    )
    return path


def choose_providers(current: dict[str, str], available: list[str]) -> dict[str, str]:
    """Ask which provider handles each role. Returns only what changed."""
    render.console.print(
        f"\n[bold]Which AI does which job[/bold] [dim](Enter = keep · options: "
        f"{', '.join(available)})[/dim]"
    )
    chosen: dict[str, str] = {}
    for role in CHOOSABLE_ROLES:
        now = current.get(role)
        if now is None:
            continue
        answer = typer.prompt(f"  {role} [{now}]", default="", show_default=False).strip()
        if answer and answer != now:
            if answer not in available:
                render.console.print(
                    f"  [yellow]unknown provider {answer!r} — keeping {now}[/yellow]"
                )
                continue
            chosen[role] = answer
    return chosen


def choose_models(
    current: dict[str, str | None], providers: list[str], commands: dict[str, str]
) -> dict[str, str]:
    """Ask which model each provider should use. '-' clears a pin.

    `commands` maps provider name to its actually-configured CLI command, so
    live discovery (e.g. `agy models`) queries what the project really runs,
    not just the provider's usual default.
    """
    render.console.print(
        "\n[bold]Model per provider[/bold] [dim](Enter = keep · '-' = use the CLI's "
        "own setting)[/dim]"
    )
    chosen: dict[str, str] = {}
    for provider in providers:
        now = current.get(provider) or "CLI default"
        command = commands.get(provider, provider)
        suggestions = model_catalog.suggestions_for(provider, command)
        if hint := model_catalog.hint_for(provider):
            render.console.print(f"  [dim]{hint}[/dim]")
        label = f"  {provider} [{now}]"
        if suggestions:
            label += f" ({'/'.join(suggestions)})"
        answer = typer.prompt(label, default="", show_default=False).strip()
        if answer:
            chosen[provider] = answer
    return chosen


def apply_choices(
    document: dict, roles: dict[str, str], models: dict[str, str]
) -> dict:
    """Merge choices into the parsed config document. Pure — unit testable.

    A model answer of '-' removes the pin so the provider falls back to whatever
    that CLI is configured to do, which is baton's default posture (ADR-031).
    """
    for role, provider in roles.items():
        document.setdefault("roles", {}).setdefault(role, {})["provider"] = provider
    for provider, model in models.items():
        block = document.setdefault("providers", {}).setdefault(provider, {})
        if model == "-":
            block.pop("model", None)
            if not block:
                document["providers"].pop(provider)
        else:
            block["model"] = model
    if not document.get("providers"):
        document.pop("providers", None)
    return document


def setup() -> None:
    """Change which AI handles each role, and which model each provider uses."""
    project_dir = Path.cwd()
    try:
        loaded = load_config(project_dir)
    except ConfigError as exc:
        render.render_error(str(exc))
        raise typer.Exit(code=2) from exc

    available = sorted(load_all().names())
    current_roles = {name: role.provider for name, role in loaded.config.roles.items()}
    current_models = {name: cfg.model for name, cfg in loaded.config.providers.items()}

    render.console.print("[bold]current setup[/bold]")
    for role in CHOOSABLE_ROLES:
        if provider := current_roles.get(role):
            model = current_models.get(provider) or "CLI default"
            enabled = loaded.config.roles[role].enabled
            suffix = "" if enabled else " [dim](disabled)[/dim]"
            render.console.print(f"  {role:<10} {provider:<14} {model}{suffix}")

    roles = choose_providers(current_roles, available)
    # Only ask about models for providers that will actually be used afterwards.
    # A set, not a list: planner and reviewer share codex by default, and asking
    # about the same provider three times exhausts piped input and aborts.
    effective = {**current_roles, **roles}
    in_use = sorted({effective[r] for r in CHOOSABLE_ROLES if r in effective})
    commands = {
        name: cfg.command for name, cfg in loaded.config.providers.items() if name in in_use
    }
    models = choose_models(current_models, in_use, commands)

    if not roles and not models:
        render.console.print("\nnothing changed.")
        return

    document = apply_choices(_load_document(project_dir), roles, models)
    render.console.print(
        "\n[dim]writing .ai/config.yaml — it is re-serialised from the parsed "
        "document, so any comments in it are dropped.[/dim]"
    )
    path = _write_document(project_dir, document)
    for role, provider in roles.items():
        render.console.print(f"  [green]{role}[/green] → {provider}")
    for provider, model in models.items():
        shown = "CLI default" if model == "-" else model
        render.console.print(f"  [green]{provider}[/green] model → {shown}")
    render.console.print(f"\nsaved {path}. `batonai config show` to verify.")
