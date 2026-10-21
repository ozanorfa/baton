"""Claude Code adapter: `claude -p --output-format json` (ARCHITECTURE.md §3.2).

Output is structured JSON with result text, session_id, measured token usage
and cost. Verified against claude 2.1.207 (fixtures in tests/contract/).

Known protocol gap (captured in permission_block.json): a permission-blocked
run exits 0 with is_error=false — the model just says it needs approval and
does nothing. Adapters cannot detect this; the engine's stage-level diff
check does (T26). Coder runs therefore always pass allow_edits.

Command access (ADR-034). `--permission-mode acceptEdits` auto-approves file
edits only; in headless mode every Bash call is then *denied*, so the Coder
cannot run tests or the app to verify its work, and the prompt's "verify what
you build" is unfulfillable. `providers: {claude: {allow_commands: true}}`
adds `--allowedTools Bash` — and, because that would otherwise be a blanket
grant, pairs it with an explicit `--disallowedTools` list that keeps git
history and remotes out of reach, so ADR-014's "no stage ever commits" holds
mechanically and not just by instruction. Disallowed rules take precedence
over allowed ones in Claude Code.
"""

import json
from pathlib import Path

from ai_orchestrator.core.models import AgentRequest, AgentResult, Capabilities, Health, Usage
from ai_orchestrator.providers.base import ProviderAdapter
from ai_orchestrator.providers.registry import registry
from ai_orchestrator.transport.base import Invocation, Transport, TransportResult

# What a Coder may never do even with command access: anything that rewrites
# history, moves the user's working tree out from under them, or reaches a
# remote. Tool-rule syntax per `claude --help` (prefix match on the command).
FORBIDDEN_COMMANDS: tuple[str, ...] = (
    "Bash(git commit:*)",
    "Bash(git push:*)",
    "Bash(git reset:*)",
    "Bash(git checkout:*)",
    "Bash(git switch:*)",
    "Bash(git restore:*)",
    "Bash(git stash:*)",
    "Bash(git rebase:*)",
    "Bash(git merge:*)",
    "Bash(git tag:*)",
    "Bash(git branch:*)",
    "Bash(git clean:*)",
    "Bash(gh:*)",
)


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
            if self.allow_commands:
                argv += ["--allowedTools", "Bash"]
                argv += ["--disallowedTools", ",".join(FORBIDDEN_COMMANDS)]
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
            data = None
        if not isinstance(data, dict):
            # Not JSON, or JSON that isn't the result object (a bare list or
            # string) — both are "the CLI did not speak the protocol".
            return AgentResult(
                success=False,
                text=raw.stdout,
                error="unparseable claude output (expected a JSON object); "
                "see raw output on disk",
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
        text = data.get("result")
        text = text if isinstance(text, str) else ("" if text is None else json.dumps(text))
        return AgentResult(
            success=not is_error,
            text=text,
            session_id=data.get("session_id"),
            usage=usage,
            error=text if is_error else None,
        )
