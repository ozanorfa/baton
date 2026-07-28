"""Transport contract: process mechanics, nothing about AI (ARCHITECTURE.md §3.3).

Adapters build an Invocation; a Transport executes it. Prompts travel on
stdin, never argv (ADR-010).
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

# ADR-030: called with each stdout line while the process runs, so a caller can
# surface progress. Optional everywhere — when it is None the transport takes
# its original single-call path, so existing behaviour is untouched.
LineSink = Callable[[str], None]


@dataclass(frozen=True)
class Invocation:
    argv: list[str]  # flags only — never prompt text
    stdin: str  # the prompt payload
    workdir: Path
    timeout_s: int
    env: dict[str, str] = field(default_factory=dict)  # additions to the inherited env


@dataclass(frozen=True)
class TransportResult:
    exit_code: int | None  # None = did not run (binary missing) or timed out
    stdout: str
    stderr: str
    duration_s: float
    timed_out: bool = False
    error: str | None = None  # transport-level failure description

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out and self.error is None


class Transport(Protocol):
    def run(
        self, invocation: Invocation, on_line: LineSink | None = None
    ) -> TransportResult: ...
