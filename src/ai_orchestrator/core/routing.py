"""Routing engine (ARCHITECTURE.md §2.3): role → adapter, resolved up front.

Every stage is resolved and every distinct provider health-checked before any
stage runs — a pipeline must never die at stage 3 for something detectable at
stage 0. Pure config-driven; no model ever routes (ADR-004).
"""

from dataclasses import dataclass

from ai_orchestrator.config.schema import AppConfig
from ai_orchestrator.context.contracts import contract_for
from ai_orchestrator.core.models import StageSpec
from ai_orchestrator.providers.base import ProviderAdapter
from ai_orchestrator.providers.registry import ProviderRegistry, UnknownProviderError
from ai_orchestrator.transport.base import Transport


class RoutingError(Exception):
    """Raised before any stage runs; names role, provider, and failing check."""


@dataclass(frozen=True)
class ResolvedStage:
    spec: StageSpec
    provider_name: str
    adapter: ProviderAdapter
    timeout_s: int
    enabled: bool
    allow_edits: bool


def build_stage_specs(config: AppConfig) -> list[StageSpec]:
    """Stage list is data from config, never runtime logic (ADR-004).
    Inputs/outputs come from the role contracts (context/contracts.py)."""
    specs: list[StageSpec] = []
    previous_output: str | None = None
    for name in config.pipeline.stages:
        contract = contract_for(name, previous_output)
        specs.append(
            StageSpec(
                name=name,
                role=name,
                optional=not config.roles[name].enabled,
                inputs=list(contract.inputs),
                output=contract.output,
            )
        )
        previous_output = contract.output
    return specs


class RoutingEngine:
    def __init__(self, config: AppConfig, registry: ProviderRegistry):
        self.config = config
        self.registry = registry

    def resolve(self, specs: list[StageSpec], transport: Transport) -> list[ResolvedStage]:
        adapters: dict[str, ProviderAdapter] = {}  # one instance per provider
        resolved: list[ResolvedStage] = []

        for spec in specs:
            role_cfg = self.config.roles[spec.role]  # schema guarantees existence
            provider_cfg = self.config.providers[role_cfg.provider]
            if role_cfg.provider not in adapters:
                try:
                    adapter_cls = self.registry.get(role_cfg.provider)
                except UnknownProviderError as exc:
                    raise RoutingError(
                        f"stage {spec.name!r} is bound to provider {role_cfg.provider!r}, "
                        f"which has no registered adapter: {exc}"
                    ) from exc
                adapters[role_cfg.provider] = adapter_cls(
                    command=provider_cfg.command, model=provider_cfg.model
                )
            allow_edits = contract_for(spec.role).allow_edits
            resolved.append(
                ResolvedStage(
                    spec=spec,
                    provider_name=role_cfg.provider,
                    adapter=adapters[role_cfg.provider],
                    timeout_s=provider_cfg.timeout_s,
                    enabled=role_cfg.enabled,
                    allow_edits=allow_edits,
                )
            )

        # Health-check each distinct provider exactly once, only for stages that will run.
        active = {r.provider_name: r.adapter for r in resolved if r.enabled}
        for provider_name, adapter in active.items():
            health = adapter.health_check(transport)
            if not health.ok:
                stages = [r.spec.name for r in resolved if r.provider_name == provider_name]
                raise RoutingError(
                    f"provider {provider_name!r} (used by: {', '.join(stages)}) failed its "
                    f"health check: {health.detail or 'unavailable'}"
                )
        return resolved
