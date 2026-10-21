"""Contract tests: DeterministicAdapter — the zero-LLM Publisher floor (ADR-018, ADR-034).

Input is `git status --porcelain -z` (NUL-separated), which — unlike the old
`git diff --stat` — also lists brand-new untracked files.
"""

from pathlib import Path

from ai_orchestrator.core.models import AgentRequest
from ai_orchestrator.providers.deterministic import DeterministicAdapter, message_from_status
from ai_orchestrator.transport.base import TransportResult

adapter = DeterministicAdapter(command="git")

MIXED = " M docs/A.md\0 M src/b.py\0"
DOCS_ONLY = " M docs/A.md\0 M README.md\0"
SINGLE_SCOPE = " M src/x.py\0?? src/y.py\0"
NEW_FILE_ONLY = "?? src/brand_new.py\0"


def request(**kw) -> AgentRequest:
    defaults = dict(role="publisher", prompt="draft it", workdir=Path("/tmp/p"), timeout_s=60)
    return AgentRequest(**{**defaults, **kw})


def test_message_infers_docs_type_when_all_docs() -> None:
    msg = message_from_status(DOCS_ONLY)
    assert msg.startswith("docs:")  # README.md + docs/ → docs, no common top-level scope
    assert "2 files changed" in msg
    assert "- docs/A.md (modified)" in msg and "- README.md (modified)" in msg


def test_message_scopes_to_common_top_dir() -> None:
    msg = message_from_status(SINGLE_SCOPE)
    assert msg.startswith("chore(src): update src")
    assert "1 added, 1 modified" in msg


def test_message_falls_back_to_chore_and_count_when_mixed() -> None:
    msg = message_from_status(MIXED)
    # docs/ + src/ → no single scope, not all-docs → generic chore with file count
    assert msg.startswith("chore: update 2 files")


def test_message_handles_clean_tree() -> None:
    msg = message_from_status("")
    assert msg.startswith("chore: no file changes detected")


def test_untracked_new_file_is_seen() -> None:
    """The reason for the ADR-034 change: a Coder that only adds a file."""
    msg = message_from_status(NEW_FILE_ONLY)
    assert "brand_new.py (added)" in msg
    assert "no file changes" not in msg


def test_message_handles_rename_records() -> None:
    msg = message_from_status("R  src/new.py\0src/old.py\0")
    assert "- src/new.py (renamed)" in msg and "old.py" not in msg


def test_message_keeps_paths_with_spaces() -> None:
    msg = message_from_status("?? my new file.py\0")
    assert "- my new file.py (added)" in msg


def test_parse_success_builds_message_from_git_stdout() -> None:
    raw = TransportResult(exit_code=0, stdout=SINGLE_SCOPE, stderr="", duration_s=0.1)
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


def test_build_invocation_runs_git_status_no_model_call() -> None:
    inv = adapter.build_invocation(request())
    assert inv.argv[:6] == ["git", "status", "--porcelain", "-z", "-uall", "--"]
    assert ":(exclude).ai" in inv.argv  # baton's own files never become "the change"
    assert inv.workdir == Path("/tmp/p")
    assert inv.stdin == ""  # no prompt — nothing for a model to read
