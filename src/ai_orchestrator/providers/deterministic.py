"""Zero-LLM Publisher adapter: a conventional-commit message from the diff (ADR-018).

The *floor* under the Publisher role — **no model, no quota, no rate limit**. Select
it per project when even a free tier is overkill or throttled:

    roles: {publisher: {provider: deterministic}}

It stays inside the pure-adapter contract by delegating the one side effect (reading
the diff) to the transport: `build_invocation` returns a `git diff HEAD --stat`
command, `parse` turns that diffstat into the message. The stat→message transform
(`message_from_diffstat`) is a pure function, unit-tested directly on fixture text.

Deterministic, so intent it cannot know is not invented: the commit *type* is inferred
only where the paths make it unambiguous (all docs → `docs`, all tests → `test`,
otherwise `chore`); the *scope* is the common top-level directory when there is one.
Known floor limitation: `git diff HEAD` does not see brand-new untracked files — a
frontier Publisher would; this is the trade for zero cost.
"""

from pathlib import Path

from ai_orchestrator.core.models import AgentRequest, AgentResult, Capabilities, Health
from ai_orchestrator.providers.base import ProviderAdapter
from ai_orchestrator.providers.registry import registry
from ai_orchestrator.transport.base import Invocation, Transport, TransportResult


def _changed_paths(stat: str) -> list[str]:
    """The file paths from `git diff --stat` output (the lines before the ` | `)."""
    paths = []
    for line in stat.splitlines():
        if "|" not in line:
            continue  # the trailing "N files changed, ..." summary has no pipe
        left = line.split("|", 1)[0].strip()
        if not left:
            continue
        # renames render as "old => new" or "dir/{a => b}/file"; take the new path
        if "=>" in left:
            left = left.replace("{", "").replace("}", "")
            left = left.split("=>", 1)[1].strip().replace("//", "/")
        paths.append(left)
    return paths


def _infer_type(paths: list[str]) -> str:
    if paths and all(p.startswith("docs/") or p.endswith(".md") for p in paths):
        return "docs"
    if paths and all(p.startswith("tests/") or "/tests/" in p for p in paths):
        return "test"
    return "chore"


def _common_scope(paths: list[str]) -> str | None:
    tops = set()
    for p in paths:
        if "/" not in p:
            return None  # a repo-root file means the changes don't share one scope
        tops.add(p.split("/", 1)[0])
    return next(iter(tops)) if len(tops) == 1 else None


def message_from_diffstat(stat: str) -> str:
    """Pure transform: `git diff --stat` text → a conventional-commit message."""
    paths = _changed_paths(stat)
    if not paths:
        return "chore: no file changes detected\n\n(No tracked changes vs HEAD.)"
    ctype = _infer_type(paths)
    scope = _common_scope(paths)
    header = f"{ctype}({scope}): update {scope}" if scope else f"{ctype}: update {len(paths)} files"
    summary = next(
        (ln.strip() for ln in stat.splitlines() if "files changed" in ln or "file changed" in ln),
        "",
    )
    body_lines = [f"- {p}" for p in paths]
    parts = [header]
    if summary:
        parts.append(summary)
    parts.append("Files:\n" + "\n".join(body_lines))
    return "\n\n".join(parts)


@registry.register
class DeterministicAdapter(ProviderAdapter):
    name = "deterministic"
    capabilities = Capabilities(supports_resume=False, reports_tokens=False, edits_files=False)

    def health_check(self, transport: Transport) -> Health:
        raw = transport.run(
            Invocation(argv=[self.command, "--version"], stdin="", workdir=Path.cwd(), timeout_s=30)
        )
        if not raw.ok:
            return Health(ok=False, binary=self.command, detail=raw.error or raw.stderr.strip())
        return Health(ok=True, binary=self.command, version=raw.stdout.strip())

    def build_invocation(self, request: AgentRequest) -> Invocation:
        # The prompt is intentionally unused — the message is derived from the diff,
        # not from a model reading the assembled context.
        return Invocation(
            argv=[self.command, "diff", "HEAD", "--stat"],
            stdin="",
            workdir=request.workdir,
            timeout_s=request.timeout_s,
        )

    def parse(self, raw: TransportResult) -> AgentResult:
        if raw.error is not None or raw.timed_out:
            return AgentResult(success=False, error=raw.error, text=raw.stdout)
        if raw.exit_code != 0:
            detail = raw.stderr.strip() or f"git diff exit code {raw.exit_code}"
            return AgentResult(success=False, text=raw.stdout, error=detail)
        return AgentResult(success=True, text=message_from_diffstat(raw.stdout))
