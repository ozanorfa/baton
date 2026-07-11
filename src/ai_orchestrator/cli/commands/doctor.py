"""`ai doctor` — verify every configured provider before spending tokens."""

import typer

from ai_orchestrator.cli import render
from ai_orchestrator.config.loader import ConfigError, load_config
from ai_orchestrator.core.models import Health
from ai_orchestrator.providers import load_all
from ai_orchestrator.providers.registry import UnknownProviderError
from ai_orchestrator.transport.headless import HeadlessTransport


def doctor() -> None:
    """Check each configured provider: binary present, version, registered adapter."""
    try:
        loaded = load_config()
    except ConfigError as exc:
        render.render_error(str(exc))
        raise typer.Exit(code=2) from exc

    registry = load_all()
    transport = HeadlessTransport()

    used_by: dict[str, list[str]] = {}
    for role_name, role in loaded.config.roles.items():
        used_by.setdefault(role.provider, []).append(role_name)

    rows: list[render.DoctorRow] = []
    for name, provider_cfg in loaded.config.providers.items():
        try:
            adapter_cls = registry.get(name)
        except UnknownProviderError as exc:
            rows.append(
                render.DoctorRow(
                    provider=name,
                    command=provider_cfg.command,
                    roles=used_by.get(name, []),
                    health=Health(ok=False, detail=str(exc)),
                )
            )
            continue
        adapter = adapter_cls(command=provider_cfg.command, model=provider_cfg.model)
        rows.append(
            render.DoctorRow(
                provider=name,
                command=provider_cfg.command,
                roles=used_by.get(name, []),
                health=adapter.health_check(transport),
            )
        )

    render.render_doctor(rows)
    if not all(row.health.ok for row in rows):
        raise typer.Exit(code=1)
