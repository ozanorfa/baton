"""Test-only provider adapter for the fake AI CLI (T18).

Registered through the real entry-point mechanism (see the dist-info next to
this file) — no test-only code paths exist in src/.
"""

from pathlib import Path

from ai_orchestrator.core.models import AgentRequest, AgentResult, Capabilities, Health
from ai_orchestrator.providers.base import ProviderAdapter
from ai_orchestrator.transport.base import Invocation, Transport, TransportResult


class FakeAdapter(ProviderAdapter):
    name = "fake"
    capabilities = Capabilities(edits_files=True)

    def health_check(self, transport: Transport) -> Health:
        raw = transport.run(
            Invocation(argv=[self.command, "--version"], stdin="", workdir=Path.cwd(), timeout_s=10)
        )
        if not raw.ok:
            return Health(ok=False, binary=self.command, detail=raw.error or raw.stderr.strip())
        return Health(ok=True, binary=self.command, version=raw.stdout.strip())

    def build_invocation(self, request: AgentRequest) -> Invocation:
        return Invocation(
            argv=[self.command],
            stdin=request.prompt,
            workdir=request.workdir,
            timeout_s=request.timeout_s,
        )

    def parse(self, raw: TransportResult) -> AgentResult:
        if raw.error is not None or raw.timed_out:
            return AgentResult(success=False, error=raw.error, text=raw.stdout)
        if raw.exit_code != 0:
            return AgentResult(success=False, text=raw.stdout, error=raw.stderr.strip())
        return AgentResult(success=True, text=raw.stdout.strip())
