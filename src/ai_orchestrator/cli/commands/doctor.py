"""`batonai doctor` — verify every configured provider before spending tokens.

Required vs optional (ADR-034 docs pass): a provider is *required* when at
least one enabled role in the pipeline's stage list is bound to it; every other
configured provider (e.g. `opencode` while the Publisher is off, `antigravity`
while the Designer is off) is *optional*. Optional providers are still probed
and shown — so a user sees what would be needed to turn a stage on — but they
never make `doctor` exit non-zero. Before this, a freshly installed baton
reported failure on a machine that was perfectly able to run the default
pipeline, just because a free client it never calls was missing.
"""

import typer

from ai_orchestrator.cli import render
from ai_orchestrator.config.loader import ConfigError, load_config
from ai_orchestrator.config.schema import AppConfig
from ai_orchestrator.core.models import Health
from ai_orchestrator.providers import load_all
from ai_orchestrator.providers.registry import UnknownProviderError
from ai_orchestrator.transport.headless import HeadlessTransport


def required_providers(config: AppConfig) -> set[str]:
    """Providers bound to roles that will actually run: in the stage list AND enabled."""
    return {
        config.roles[stage].provider
        for stage in config.pipeline.stages
        if stage in config.roles and config.roles[stage].enabled
    }


def doctor() -> None:
    """Check each configured provider: binary present, version, registered adapter."""
    try:
        loaded = load_config()
    except ConfigError as exc:
        render.render_error(str(exc))
        raise typer.Exit(code=2) from exc

    registry = load_all()
    transport = HeadlessTransport()
    required = required_providers(loaded.config)

    used_by: dict[str, list[str]] = {}
    for role_name, role in loaded.config.roles.items():
        label = role_name if role.enabled else f"{role_name} (off)"
        used_by.setdefault(role.provider, []).append(label)

    rows: list[render.DoctorRow] = []
    for name, provider_cfg in loaded.config.providers.items():
        try:
            adapter_cls = registry.get(name)
        except UnknownProviderError as exc:
            health = Health(ok=False, detail=str(exc))
        else:
            adapter = adapter_cls.configure(
                provider_cfg.command, provider_cfg.model, provider_cfg.allow_commands
            )
            health = adapter.health_check(transport)
        rows.append(
            render.DoctorRow(
                provider=name,
                command=provider_cfg.command,
                roles=used_by.get(name, []),
                health=health,
                required=name in required,
            )
        )

    render.render_doctor(rows)
    if not all(row.health.ok for row in rows if row.required):
        raise typer.Exit(code=1)
