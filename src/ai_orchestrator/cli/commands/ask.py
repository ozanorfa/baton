"""`ai ask` — one-shot single-role invocation. The manual escape hatch (ADR-004)."""

from pathlib import Path

import typer

from ai_orchestrator.cli import render
from ai_orchestrator.config.loader import ConfigError, load_config
from ai_orchestrator.core.models import AgentRequest
from ai_orchestrator.providers import load_all
from ai_orchestrator.providers.base import invoke
from ai_orchestrator.providers.registry import UnknownProviderError
from ai_orchestrator.transport.headless import HeadlessTransport


def ask(
    prompt: str = typer.Argument(..., help="The prompt to send."),
    role: str = typer.Option(..., "--role", help="Role whose provider binding to use."),
) -> None:
    """Send one prompt through a role's configured provider. No pipeline, no artifacts."""
    try:
        loaded = load_config()
    except ConfigError as exc:
        render.render_error(str(exc))
        raise typer.Exit(code=2) from exc

    role_cfg = loaded.config.roles.get(role)
    if role_cfg is None:
        render.render_error(
            f"unknown role {role!r}; configured roles: {sorted(loaded.config.roles)}"
        )
        raise typer.Exit(code=2)

    provider_cfg = loaded.config.providers[role_cfg.provider]
    try:
        adapter_cls = load_all().get(role_cfg.provider)
    except UnknownProviderError as exc:
        render.render_error(str(exc))
        raise typer.Exit(code=2) from exc

    adapter = adapter_cls(command=provider_cfg.command, model=provider_cfg.model)
    request = AgentRequest(
        role=role,
        prompt=prompt,
        workdir=Path.cwd(),
        timeout_s=provider_cfg.timeout_s,
        allow_edits=False,  # ask is always advisory — pipeline stages decide edits
    )
    render.console.print(
        f"[dim]{role} → {role_cfg.provider} ({provider_cfg.command}), "
        f"timeout {provider_cfg.timeout_s}s…[/dim]"
    )
    result = invoke(adapter, HeadlessTransport(), request)

    if not result.success:
        render.render_error(f"provider failed: {result.error or 'unknown error'}")
        if result.text:
            render.console.print(result.text)
        raise typer.Exit(code=1)

    render.console.print(result.text)
    render.render_usage_line(result)
