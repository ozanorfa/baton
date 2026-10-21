"""Zero-LLM Publisher adapter: a conventional-commit message from the working tree (ADR-018).

The *floor* under the Publisher role — **no model, no quota, no rate limit**. Select
it per project when even a free tier is overkill or throttled:

    roles: {publisher: {provider: deterministic}}

It stays inside the pure-adapter contract by delegating the one side effect (reading
the tree) to the transport: `build_invocation` returns a `git status --porcelain -z`
command, `parse` turns that listing into the message. The listing→message transform
(`message_from_status`) is a pure function, unit-tested directly on fixture text.

Deterministic, so intent it cannot know is not invented: the commit *type* is inferred
only where the paths make it unambiguous (all docs → `docs`, all tests → `test`,
otherwise `chore`); the *scope* is the common top-level directory when there is one.

ADR-034: this used to read `git diff HEAD --stat`, which cannot see brand-new
untracked files — so a Coder whose whole change was a new module got "no file
changes detected". `git status` lists added, modified, deleted and untracked
files alike, with the same `.ai/`/generated-file exclusions the diff capture uses.
"""

from pathlib import Path

from ai_orchestrator.core.models import AgentRequest, AgentResult, Capabilities, Health
from ai_orchestrator.core.workspace import EXCLUDE_PATHSPECS, parse_porcelain_z
from ai_orchestrator.providers.base import ProviderAdapter
from ai_orchestrator.providers.registry import registry
from ai_orchestrator.transport.base import Invocation, Transport, TransportResult

_KIND_LABEL = {"A": "added", "?": "added", "M": "modified", "D": "deleted", "R": "renamed",
               "C": "copied", "T": "type-changed", "U": "conflicted"}


def _changed_paths(porcelain_z: str) -> list[tuple[str, str]]:
    """(path, change kind) for every entry; a rename's path is the NEW name."""
    changed: list[tuple[str, str]] = []
    for xy, path in parse_porcelain_z(porcelain_z):
        code = xy[1] if xy[0] in " ?" else xy[0]  # worktree column, else index column
        changed.append((path, _KIND_LABEL.get(code, "modified")))
    return changed


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


def _summary(changes: list[tuple[str, str]]) -> str:
    counts: dict[str, int] = {}
    for _, kind in changes:
        counts[kind] = counts.get(kind, 0) + 1
    parts = [f"{n} {kind}" for kind, n in sorted(counts.items())]
    noun = "file" if len(changes) == 1 else "files"
    return f"{len(changes)} {noun} changed ({', '.join(parts)})"


def message_from_status(porcelain_z: str) -> str:
    """Pure transform: `git status --porcelain -z` text → a conventional-commit message."""
    changes = _changed_paths(porcelain_z)
    if not changes:
        return "chore: no file changes detected\n\n(Working tree matches HEAD.)"
    paths = [p for p, _ in changes]
    ctype = _infer_type(paths)
    scope = _common_scope(paths)
    noun = "file" if len(paths) == 1 else "files"
    header = (
        f"{ctype}({scope}): update {scope}" if scope
        else f"{ctype}: update {len(paths)} {noun}"
    )
    body = "\n".join(f"- {p} ({kind})" for p, kind in changes)
    return "\n\n".join([header, _summary(changes), "Files:\n" + body])


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
        # The prompt is intentionally unused — the message is derived from the tree,
        # not from a model reading the assembled context.
        return Invocation(
            argv=[self.command, "status", "--porcelain", "-z", "-uall", "--", ".",
                  *EXCLUDE_PATHSPECS],
            stdin="",
            workdir=request.workdir,
            timeout_s=request.timeout_s,
        )

    def parse(self, raw: TransportResult) -> AgentResult:
        if raw.error is not None or raw.timed_out:
            return AgentResult(success=False, error=raw.error, text=raw.stdout)
        if raw.exit_code != 0:
            detail = raw.stderr.strip() or f"git status exit code {raw.exit_code}"
            return AgentResult(success=False, text=raw.stdout, error=detail)
        return AgentResult(success=True, text=message_from_status(raw.stdout))
