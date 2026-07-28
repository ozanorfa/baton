"""Provider adapter contract (ARCHITECTURE.md §3.1).

Adapters are pure: they build Invocations and parse TransportResults, and
never spawn processes themselves — that keeps every adapter unit-testable
against recorded fixtures with no subprocess (defense against risk R1).
"""

from abc import ABC, abstractmethod
from typing import ClassVar

from ai_orchestrator.core.models import AgentRequest, AgentResult, Capabilities, Health
from ai_orchestrator.transport.base import Invocation, Transport, TransportResult


def _sanitize(text: str, limit: int) -> str | None:
    """Make vendor output safe to print, or None if nothing readable remains.

    ADR-030: a progress note is text a third-party process chose. It must not be
    able to move the cursor, clear the screen, or smuggle Rich markup — so
    control characters go, square brackets are neutralised, and the result is
    truncated to one short line.
    """
    flat = " ".join(text.split())
    cleaned = "".join(ch for ch in flat if ch.isprintable())
    cleaned = cleaned.replace("[", "(").replace("]", ")")
    if not cleaned:
        return None
    return cleaned[: limit - 1] + "…" if len(cleaned) > limit else cleaned


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

    def progress_note(self, line: str) -> str | None:
        """One short human note for a raw stdout line, or None (ADR-030).

        Vendor stream formats stay behind this boundary, exactly as usage
        parsing does. The default is None, so a provider that streams nothing
        keeps the plain spinner and no other layer learns about it.
        """
        return None

    @abstractmethod
    def parse(self, raw: TransportResult) -> AgentResult:
        """Normalize raw CLI output. Malformed output must yield a failed
        AgentResult, never raise — the raw material is preserved on disk."""


def invoke(adapter: ProviderAdapter, transport: Transport, request: AgentRequest) -> AgentResult:
    """The one canonical build → run → parse path (used by engine, ask, doctor)."""
    raw = adapter.build_invocation(request)
    return adapter.parse(transport.run(raw))
