"""Antigravity CLI adapter: `agy -p <prompt>` (ADR-012).

Verified against agy 1.1.1 (fixtures in tests/contract/):

- Plain-text output; no JSON mode, no session id, no token usage in print
  mode → Usage stays None (never estimated, risk R2).
- **No stdin prompt support** (`-` is taken literally) — the prompt must ride
  in argv, a documented exception to ADR-010. Safe: shell=False everywhere,
  so no interpolation; ARG_MAX is far above Designer-prompt sizes.
- `--sandbox` is incompatible with print mode ("Agent execution terminated
  due to error", exit 1) — do not pass it.
- `--print-timeout` defaults to 5m; pinned to the request timeout so agy
  doesn't give up before our transport does.
- `--conversation <id>` resume exists, but the id is not printed in -p mode,
  so resume is unreachable headlessly today: supports_resume=False.
- **`--new-project` is mandatory** (field bug, 2026-07-12): without it, agy
  loads its persistent cross-session "brain" (~/.gemini/antigravity-cli/) and
  can wander into *other* directories it remembers — a real run spawned ~60
  internal tasks referencing a different copy of the user's project, went
  silent, and timed out at 600s. Isolated sessions answer in well under 2 min.
"""

from pathlib import Path

from ai_orchestrator.core.models import AgentRequest, AgentResult, Capabilities, Health
from ai_orchestrator.providers.base import ProviderAdapter
from ai_orchestrator.providers.registry import registry
from ai_orchestrator.transport.base import Invocation, Transport, TransportResult


@registry.register
class AntigravityAdapter(ProviderAdapter):
    name = "antigravity"
    capabilities = Capabilities(supports_resume=False, reports_tokens=False, edits_files=True)

    def health_check(self, transport: Transport) -> Health:
        raw = transport.run(
            Invocation(argv=[self.command, "--version"], stdin="", workdir=Path.cwd(), timeout_s=30)
        )
        if not raw.ok:
            return Health(ok=False, binary=self.command, detail=raw.error or raw.stderr.strip())
        return Health(ok=True, binary=self.command, version=raw.stdout.strip())

    def build_invocation(self, request: AgentRequest) -> Invocation:
        argv = [self.command, "--new-project"]  # isolate from agy's brain (see docstring)
        if self.model:
            argv += ["--model", self.model]
        if request.allow_edits:
            argv += ["--mode", "accept-edits"]
        argv += ["--print-timeout", f"{request.timeout_s}s"]
        argv += ["-p", request.prompt]  # agy cannot read the prompt from stdin (see docstring)
        return Invocation(
            argv=argv,
            stdin="",
            workdir=request.workdir,
            timeout_s=request.timeout_s,
        )

    def parse(self, raw: TransportResult) -> AgentResult:
        if raw.error is not None or raw.timed_out:
            return AgentResult(success=False, error=raw.error, text=raw.stdout)
        if raw.exit_code != 0:
            detail = raw.stderr.strip() or raw.stdout.strip() or f"exit code {raw.exit_code}"
            return AgentResult(success=False, text=raw.stdout, error=detail)
        return AgentResult(success=True, text=raw.stdout.strip())
