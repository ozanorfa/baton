"""opencode CLI adapter: `opencode run -- <prompt>` (ADR-017).

Wired for the pipeline's *shallow text* jobs only — Publisher (drafts a commit
message + PR description) and `ai ask`. Never Coder/Reviewer: those see
proprietary source, and opencode's model comes from a user-configured **free
tier** (OpenRouter `:free`, Google AI Studio free-tier key, opencode promo
models). Those tiers are rate-limited and typically **may train on submitted
data** — acceptable for a commit message, not for proprietary code. The
orchestrator never pins the model; point opencode at a backend via its own
`opencode auth` / config.

Verified against opencode 1.18.4 (fixtures in tests/contract/):

- Non-interactive: `opencode run` defaults to headless (`-i/--interactive` is
  off by default). Plain-text answer on stdout; stderr carries log noise even
  when piped, so it is ignored on success (exit 0).
- **Prompt rides in argv**, not stdin — `run [message..]` is a variadic
  positional (a documented exception to ADR-010, shared with antigravity).
  Passed after a `--` separator so a prompt starting with `-` is never parsed
  as a flag; shell=False everywhere, so no interpolation risk.
- No token usage on stdout in run mode (`opencode stats` is separate) → Usage
  stays None, never estimated (risk R2). reports_tokens=False.
- Sessions exist (`-c`/`-s`) but the id is not surfaced on stdout in the
  default format, so resume is unreachable headlessly today: supports_resume=False.
- **`--auto` (tool auto-approve) and `--share` (public session upload) are never
  passed.** This adapter is text-only; the roles it serves are allow_edits=False
  by contract (publisher, ask), so edit permissions are never auto-approved —
  the ADR-014 "orchestrator never commits" guarantee holds by construction.
"""

from pathlib import Path

from ai_orchestrator.core.models import AgentRequest, AgentResult, Capabilities, Health
from ai_orchestrator.providers.base import ProviderAdapter
from ai_orchestrator.providers.registry import registry
from ai_orchestrator.transport.base import Invocation, Transport, TransportResult


@registry.register
class OpencodeAdapter(ProviderAdapter):
    name = "opencode"
    capabilities = Capabilities(supports_resume=False, reports_tokens=False, edits_files=False)

    def health_check(self, transport: Transport) -> Health:
        raw = transport.run(
            Invocation(argv=[self.command, "--version"], stdin="", workdir=Path.cwd(), timeout_s=30)
        )
        if not raw.ok:
            return Health(ok=False, binary=self.command, detail=raw.error or raw.stderr.strip())
        return Health(ok=True, binary=self.command, version=raw.stdout.strip())

    def build_invocation(self, request: AgentRequest) -> Invocation:
        argv = [self.command, "run"]
        if self.model:
            argv += ["--model", self.model]  # opencode format: provider/model
        # `--` stops option parsing; the prompt follows as the positional message
        # (opencode has no stdin prompt mode — see docstring). allow_edits is
        # intentionally ignored: this adapter never enables opencode's tools.
        argv += ["--", request.prompt]
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
