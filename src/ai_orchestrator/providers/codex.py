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
from ai_orchestrator.providers.base import ProviderAdapter, _sanitize
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
        resuming = bool(request.session_id)
        if resuming:
            argv += ["resume", request.session_id]
        argv += ["--json", "--skip-git-repo-check"]
        # `codex exec resume` does not accept -s/--sandbox at all (verified
        # 2026-07-12: "error: unexpected argument '-s' found") — a resumed
        # session keeps the sandbox mode it was created with. The engine
        # (core/engine.py, ADR-015) only chains sessions between stages with
        # matching allow_edits, so this is never a silent capability change.
        if not resuming:
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

    # Bounded on purpose (ADR-030): evidence of life and the rough shape of the
    # work, never a transcript of the model's reasoning.
    NOTE_MAX_CHARS = 90

    def progress_note(self, line: str) -> str | None:
        """Turn one `codex --json` event into a short note, or None.

        Event shapes verified against a real captured run (2026-07-28):
        `item.started`/`item.completed` carry either a shell `command` the model
        is running or its short `text`.
        """
        line = line.strip()
        if not line.startswith("{"):
            return None
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return None
        if not isinstance(event, dict) or event.get("type") != "item.started":
            return None  # one note per item; "completed" would double every line
        item = event.get("item")
        if not isinstance(item, dict):
            return None
        if command := item.get("command"):
            return _sanitize(f"$ {command}", self.NOTE_MAX_CHARS)
        if text := item.get("text"):
            return _sanitize(str(text), self.NOTE_MAX_CHARS)
        return None

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
