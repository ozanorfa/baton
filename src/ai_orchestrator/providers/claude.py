"""Claude Code adapter: `claude -p --output-format json` (ARCHITECTURE.md §3.2).

Output is structured JSON with result text, session_id, measured token usage
and cost. Verified against claude 2.1.207 (fixtures in tests/contract/).

Known protocol gap (captured in permission_block.json): a permission-blocked
run exits 0 with is_error=false — the model just says it needs approval and
does nothing. Adapters cannot detect this; the engine's stage-level diff
check does (T26). Coder runs therefore always pass allow_edits.
"""

import json
from pathlib import Path

from ai_orchestrator.core.models import AgentRequest, AgentResult, Capabilities, Health, Usage
from ai_orchestrator.providers.base import ProviderAdapter
from ai_orchestrator.providers.registry import registry
from ai_orchestrator.transport.base import Invocation, Transport, TransportResult


@registry.register
class ClaudeCodeAdapter(ProviderAdapter):
    name = "claude"
    capabilities = Capabilities(supports_resume=True, reports_tokens=True, edits_files=True)

    def health_check(self, transport: Transport) -> Health:
        raw = transport.run(
            Invocation(argv=[self.command, "--version"], stdin="", workdir=Path.cwd(), timeout_s=30)
        )
        if not raw.ok:
            return Health(ok=False, binary=self.command, detail=raw.error or raw.stderr.strip())
        return Health(ok=True, binary=self.command, version=raw.stdout.strip())

    def build_invocation(self, request: AgentRequest) -> Invocation:
        argv = [self.command, "-p", "--output-format", "json"]
        if self.model:
            argv += ["--model", self.model]
        if request.session_id:
            argv += ["--resume", request.session_id]
        if request.allow_edits:
            argv += ["--permission-mode", "acceptEdits"]
        return Invocation(
            argv=argv,
            stdin=request.prompt,
            workdir=request.workdir,
            timeout_s=request.timeout_s,
        )

    def parse(self, raw: TransportResult) -> AgentResult:
        if raw.error is not None or raw.timed_out:
            return AgentResult(success=False, error=raw.error, text=raw.stdout)
        try:
            data = json.loads(raw.stdout)
        except json.JSONDecodeError:
            return AgentResult(
                success=False,
                text=raw.stdout,
                error="unparseable claude output (expected JSON); see raw output on disk",
            )
        usage_data = data.get("usage") or {}
        input_side = sum(
            usage_data.get(k) or 0
            for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
        )
        usage = Usage(
            input_tokens=input_side if usage_data else None,
            output_tokens=usage_data.get("output_tokens"),
            cost_usd=data.get("total_cost_usd"),
        )
        is_error = bool(data.get("is_error")) or raw.exit_code != 0
        return AgentResult(
            success=not is_error,
            text=data.get("result", ""),
            session_id=data.get("session_id"),
            usage=usage,
            error=data.get("result") if is_error else None,
        )
