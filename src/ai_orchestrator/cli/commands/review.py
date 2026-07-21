"""`ai review` — send the current working-tree diff to the Reviewer (ADR-022).

A one-shot, pipeline-free review: capture the uncommitted changes (yours or a
prior run's), assemble the Reviewer's normal context around them, and print the
verdict. Like `ai ask --role reviewer`, but it auto-captures the diff and builds
the proper reviewer context. The Reviewer never edits anything (allow_edits=False).
"""

from pathlib import Path

import typer

from ai_orchestrator.cli import render
from ai_orchestrator.config.loader import ConfigError, load_config
from ai_orchestrator.context.manager import ContextManager
from ai_orchestrator.core.models import AgentRequest, StageSpec
from ai_orchestrator.core.workspace import snapshot_changes
from ai_orchestrator.providers import load_all
from ai_orchestrator.providers.base import invoke
from ai_orchestrator.providers.registry import UnknownProviderError
from ai_orchestrator.transport.headless import HeadlessTransport


def review(
    message: str = typer.Option(
        None, "-m", "--message", help="Extra instruction for the reviewer (e.g. focus on security)."
    ),
) -> None:
    """Review the current working-tree changes with the Reviewer's model."""
    project_dir = Path.cwd()

    snapshot = snapshot_changes(project_dir)
    if snapshot is None:
        render.render_error("not a git repository (or git unavailable) — nothing to diff.")
        raise typer.Exit(code=2)
    if not snapshot.changed:
        render.console.print("[yellow]nothing to review — working tree is clean.[/yellow]")
        raise typer.Exit(code=0)

    try:
        loaded = load_config(project_dir)
    except ConfigError as exc:
        render.render_error(str(exc))
        raise typer.Exit(code=2) from exc

    role_cfg = loaded.config.roles.get("reviewer")
    if role_cfg is None:
        render.render_error(
            f"no 'reviewer' role configured; configured roles: {sorted(loaded.config.roles)}"
        )
        raise typer.Exit(code=2)
    provider_cfg = loaded.config.providers[role_cfg.provider]
    try:
        adapter_cls = load_all().get(role_cfg.provider)
    except UnknownProviderError as exc:
        render.render_error(str(exc))
        raise typer.Exit(code=2) from exc

    # Assemble the Reviewer's normal context (reviewer.md template + layers),
    # feeding the captured diff as its one admitted input.
    context = ContextManager(project_dir, loaded.config.context.project_profile)
    spec = StageSpec(name="reviewer", role="reviewer", inputs=["diff.patch"], output="review.md")
    request = message or "Review the current working-tree changes."
    prompt = context.build(spec, request, {"diff.patch": snapshot.patch})

    adapter = adapter_cls(command=provider_cfg.command, model=provider_cfg.model)
    agent_request = AgentRequest(
        role="reviewer", prompt=prompt, workdir=project_dir,
        timeout_s=provider_cfg.timeout_s, allow_edits=False,
    )
    render.console.print(
        f"[dim]reviewer → {role_cfg.provider} ({provider_cfg.command}), "
        f"timeout {provider_cfg.timeout_s}s…[/dim]"
    )
    result = invoke(adapter, HeadlessTransport(), agent_request)

    if not result.success:
        render.render_error(f"provider failed: {result.error or 'unknown error'}")
        if result.text:
            render.console.print(result.text)
        raise typer.Exit(code=1)

    render.console.print(result.text)
    render.render_usage_line(result)
