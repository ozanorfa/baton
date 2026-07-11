"""Codex CLI adapter: `codex exec --json` (ARCHITECTURE.md §3.2, ADR-003).

Output is JSONL events. Verified against codex-cli 0.144.1 (fixtures in
tests/contract/): `thread.started` carries the session id (resumable via
`codex exec resume <id>`), `item.completed`/`agent_message` carries the text,
`turn.completed` carries measured token usage, `turn.failed` carries errors.

Sandbox policy maps to the role's write access: read-only for Planner and
Reviewer, workspace-write when the role edits files (ADR-007).
"""

import json
from pathlib import Path

from ai_orchestrator.core.models import AgentRequest, AgentResult, Capabilities, Health, Usage
from ai_orchestrator.providers.base import ProviderAdapter
from ai_orchestrator.providers.registry import registry
from ai_orchestrator.transport.base import Invocation, Transport, TransportResult


@registry.register
class CodexAdapter(ProviderAdapter):
    name = "codex"
    capabilities = Capabilities(supports_resume=True, reports_tokens=True, edits_files=True)

    def health_check(self, transport: Transport) -> Health:
        raw = transport.run(
            Invocation(argv=[self.command, "--version"], stdin="", workdir=Path.cwd(), timeout_s=30)
        )
        if not raw.ok:
            return Health(ok=False, binary=self.command, detail=raw.error or raw.stderr.strip())
        return Health(ok=True, binary=self.command, version=raw.stdout.strip())

    def build_invocation(self, request: AgentRequest) -> Invocation:
        argv = [self.command, "exec"]
        if request.session_id:
            argv += ["resume", request.session_id]
        argv += ["--json", "--skip-git-repo-check"]
        argv += ["-s", "workspace-write" if request.allow_edits else "read-only"]
        if self.model:
            argv += ["-m", self.model]
        argv += ["-"]  # read the prompt from stdin (ADR-010)
        return Invocation(
            argv=argv,
            stdin=request.prompt,
            workdir=request.workdir,
            timeout_s=request.timeout_s,
        )

    def parse(self, raw: TransportResult) -> AgentResult:
        if raw.error is not None or raw.timed_out:
            return AgentResult(success=False, error=raw.error, text=raw.stdout)

        session_id: str | None = None
        messages: list[str] = []
        errors: list[str] = []
        usage: Usage | None = None
        parsed_any = False

        for line in raw.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            parsed_any = True
            kind = event.get("type")
            if kind == "thread.started":
                session_id = event.get("thread_id")
            elif kind == "item.completed":
                item = event.get("item") or {}
                if item.get("type") == "agent_message":
                    messages.append(item.get("text", ""))
                elif item.get("type") == "error":
                    errors.append(item.get("message", ""))
            elif kind == "turn.completed":
                u = event.get("usage") or {}
                usage = Usage(
                    input_tokens=u.get("input_tokens"),
                    output_tokens=u.get("output_tokens"),
                )
            elif kind in ("turn.failed", "error"):
                message = event.get("message") or (event.get("error") or {}).get("message", "")
                if message:
                    errors.append(message)

        if not parsed_any:
            return AgentResult(
                success=False,
                text=raw.stdout,
                error="unparseable codex output (expected JSONL); see raw output on disk",
            )

        failed = raw.exit_code != 0
        return AgentResult(
            success=not failed,
            text="\n\n".join(messages),
            session_id=session_id,
            usage=usage,
            error="; ".join(dict.fromkeys(errors)) or None if failed else None,
        )
