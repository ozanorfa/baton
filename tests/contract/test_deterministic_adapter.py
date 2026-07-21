"""Contract tests: DeterministicAdapter — the zero-LLM Publisher floor (ADR-018)."""

from pathlib import Path

from ai_orchestrator.core.models import AgentRequest
from ai_orchestrator.providers.deterministic import DeterministicAdapter, message_from_diffstat
from ai_orchestrator.transport.base import TransportResult

adapter = DeterministicAdapter(command="git")

MIXED_STAT = (
    " docs/A.md   |  3 +-\n"
    " src/b.py    | 10 +++++-----\n"
    " 2 files changed, 8 insertions(+), 5 deletions(-)\n"
)
DOCS_ONLY_STAT = (
    " docs/A.md      |  3 +-\n"
    " README.md      |  1 +\n"
    " 2 files changed, 3 insertions(+), 1 deletion(-)\n"
)
SINGLE_SCOPE_STAT = (
    " src/x.py    | 2 +-\n"
    " src/y.py    | 4 ++--\n"
    " 2 files changed, 4 insertions(+), 2 deletions(-)\n"
)


def request(**kw) -> AgentRequest:
    defaults = dict(role="publisher", prompt="draft it", workdir=Path("/tmp/p"), timeout_s=60)
    return AgentRequest(**{**defaults, **kw})


def test_message_infers_docs_type_when_all_docs() -> None:
    msg = message_from_diffstat(DOCS_ONLY_STAT)
    assert msg.startswith("docs:")  # README.md + docs/ → docs, no common top-level scope
    assert "2 files changed" in msg
    assert "- docs/A.md" in msg and "- README.md" in msg


def test_message_scopes_to_common_top_dir() -> None:
    msg = message_from_diffstat(SINGLE_SCOPE_STAT)
    assert msg.startswith("chore(src): update src")


def test_message_falls_back_to_chore_and_count_when_mixed() -> None:
    msg = message_from_diffstat(MIXED_STAT)
    # docs/ + src/ → no single scope, not all-docs → generic chore with file count
    assert msg.startswith("chore: update 2 files")


def test_message_handles_empty_diff() -> None:
    msg = message_from_diffstat("")
    assert msg.startswith("chore: no file changes detected")


def test_message_handles_rename_arrow() -> None:
    stat = " src/{old.py => new.py} | 0\n 1 file changed, 0 insertions(+), 0 deletions(-)\n"
    msg = message_from_diffstat(stat)
    assert "new.py" in msg and "=>" not in msg


def test_parse_success_builds_message_from_git_stdout() -> None:
    raw = TransportResult(exit_code=0, stdout=SINGLE_SCOPE_STAT, stderr="", duration_s=0.1)
    result = adapter.parse(raw)
    assert result.success
    assert result.text.startswith("chore(src): update src")
    assert result.usage is None  # no model, so no tokens — honest None


def test_parse_git_failure_surfaces_stderr() -> None:
    raw = TransportResult(
        exit_code=128, stdout="", stderr="fatal: not a git repository", duration_s=0.1
    )
    result = adapter.parse(raw)
    assert not result.success
    assert "not a git repository" in result.error


def test_build_invocation_runs_git_diff_stat_no_model_call() -> None:
    inv = adapter.build_invocation(request())
    assert inv.argv == ["git", "diff", "HEAD", "--stat"]
    assert inv.workdir == Path("/tmp/p")
