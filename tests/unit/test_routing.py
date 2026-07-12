from importlib.resources import files

import pytest
import yaml

from ai_orchestrator.config.schema import AppConfig
from ai_orchestrator.core.models import Capabilities, Health
from ai_orchestrator.core.routing import RoutingEngine, RoutingError, build_stage_specs
from ai_orchestrator.providers.base import ProviderAdapter
from ai_orchestrator.providers.registry import ProviderRegistry


class StubAdapter(ProviderAdapter):
    name = "stub"
    capabilities = Capabilities()
    healthy = True

    def health_check(self, transport):
        if self.healthy:
            return Health(ok=True, binary=self.command, version="1.0")
        return Health(ok=False, binary=self.command, detail="not authenticated")

    def build_invocation(self, request):
        raise NotImplementedError

    def parse(self, raw):
        raise NotImplementedError


def make_config(**provider_overrides) -> AppConfig:
    data = yaml.safe_load((files("ai_orchestrator.config") / "defaults.yaml").read_text())
    for role in data["roles"].values():
        role["provider"] = "stub"
    data["providers"] = {"stub": {"command": "stub-bin", **provider_overrides}}
    return AppConfig.model_validate(data)


def make_registry(adapter_cls=StubAdapter) -> ProviderRegistry:
    reg = ProviderRegistry()
    reg.register(adapter_cls)
    return reg


def test_build_stage_specs_from_default_pipeline() -> None:
    specs = build_stage_specs(make_config())
    assert [s.name for s in specs] == ["planner", "designer", "coder", "reviewer", "publisher"]
    assert specs[1].optional  # designer disabled by default
    assert specs[4].optional  # publisher disabled by default (ADR-014)
    assert specs[2].inputs == ["plan.md", "design.md"]
    assert specs[3].output == "review.md"
    assert specs[4].inputs == ["changes.md", "diff.patch", "review.md"]


def test_unknown_role_gets_generic_chain_spec() -> None:
    config = make_config()
    config.pipeline.stages.append("tester")
    config.roles["tester"] = config.roles["planner"]
    specs = build_stage_specs(config)
    tester = specs[-1]
    assert tester.output == "tester.md"
    assert tester.inputs == ["commit_message.md"]  # consumes the previous stage's artifact


def test_resolve_shares_one_adapter_per_provider() -> None:
    engine = RoutingEngine(make_config(), make_registry())
    resolved = engine.resolve(build_stage_specs(make_config()), transport=None)
    adapters = {id(r.adapter) for r in resolved}
    assert len(adapters) == 1  # all five roles → same provider → same instance
    assert resolved[2].allow_edits and not resolved[0].allow_edits
    assert resolved[2].timeout_s == 600


def test_misbound_role_fails_at_resolve_named() -> None:
    engine = RoutingEngine(make_config(), ProviderRegistry())  # empty registry
    with pytest.raises(RoutingError, match=r"stage 'planner'.*provider 'stub'"):
        engine.resolve(build_stage_specs(make_config()), transport=None)


def test_unhealthy_provider_fails_before_any_stage() -> None:
    class Sick(StubAdapter):
        healthy = False

    engine = RoutingEngine(make_config(), make_registry(Sick))
    with pytest.raises(RoutingError, match=r"'stub' \(used by: planner.*not authenticated"):
        engine.resolve(build_stage_specs(make_config()), transport=None)


def test_disabled_stage_provider_is_not_health_checked() -> None:
    """A disabled designer must not block the run even if its provider is sick."""
    config = make_config()
    calls: list[str] = []

    class Tracking(StubAdapter):
        def health_check(self, transport):
            calls.append(self.command)
            return super().health_check(transport)

    engine = RoutingEngine(config, make_registry(Tracking))
    engine.resolve(build_stage_specs(config), transport=None)
    assert len(calls) == 1  # one distinct active provider, checked exactly once
