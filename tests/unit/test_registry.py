from pathlib import Path

import pytest

from ai_orchestrator.core.models import AgentRequest, AgentResult, Capabilities, Health
from ai_orchestrator.providers.base import ProviderAdapter, invoke
from ai_orchestrator.providers.registry import ProviderRegistry, UnknownProviderError
from ai_orchestrator.transport.base import Invocation, TransportResult


class DummyAdapter(ProviderAdapter):
    name = "dummy"
    capabilities = Capabilities()

    def health_check(self, transport) -> Health:
        return Health(ok=True, binary=self.command)

    def build_invocation(self, request: AgentRequest) -> Invocation:
        return Invocation(
            argv=[self.command, "--flag"],
            stdin=request.prompt,
            workdir=request.workdir,
            timeout_s=request.timeout_s,
        )

    def parse(self, raw: TransportResult) -> AgentResult:
        return AgentResult(success=raw.ok, text=raw.stdout)


class FakeTransport:
    def run(self, invocation: Invocation, on_line=None) -> TransportResult:
        return TransportResult(
            exit_code=0, stdout=f"echo:{invocation.stdin}", stderr="", duration_s=0.01
        )


def test_register_and_resolve() -> None:
    reg = ProviderRegistry()
    reg.register(DummyAdapter)
    assert reg.get("dummy") is DummyAdapter
    assert reg.names() == ["dummy"]


def test_unknown_provider_lists_registered() -> None:
    reg = ProviderRegistry()
    reg.register(DummyAdapter)
    with pytest.raises(UnknownProviderError, match=r"'mystery'.*\['dummy'\]"):
        reg.get("mystery")


def test_invoke_helper_runs_build_run_parse() -> None:
    adapter = DummyAdapter(command="dummy-bin")
    request = AgentRequest(role="planner", prompt="hi", workdir=Path("/tmp"), timeout_s=5)
    result = invoke(adapter, FakeTransport(), request)
    assert result.success
    assert result.text == "echo:hi"
