"""Provider adapter contract (ARCHITECTURE.md §3.1).

Adapters are pure: they build Invocations and parse TransportResults, and
never spawn processes themselves — that keeps every adapter unit-testable
against recorded fixtures with no subprocess (defense against risk R1).
"""

from abc import ABC, abstractmethod
from typing import ClassVar

from ai_orchestrator.core.models import AgentRequest, AgentResult, Capabilities, Health
from ai_orchestrator.transport.base import Invocation, Transport, TransportResult


class ProviderAdapter(ABC):
    name: ClassVar[str]
    capabilities: ClassVar[Capabilities]

    def __init__(self, command: str, model: str | None = None):
        self.command = command
        self.model = model

    @abstractmethod
    def health_check(self, transport: Transport) -> Health:
        """Binary present, version parseable, auth OK (where cheap to probe)."""

    @abstractmethod
    def build_invocation(self, request: AgentRequest) -> Invocation:
        """Flags in argv, prompt on stdin (ADR-010). No process is spawned here."""

    @abstractmethod
    def parse(self, raw: TransportResult) -> AgentResult:
        """Normalize raw CLI output. Malformed output must yield a failed
        AgentResult, never raise — the raw material is preserved on disk."""


def invoke(adapter: ProviderAdapter, transport: Transport, request: AgentRequest) -> AgentResult:
    """The one canonical build → run → parse path (used by engine, ask, doctor)."""
    raw = adapter.build_invocation(request)
    return adapter.parse(transport.run(raw))
