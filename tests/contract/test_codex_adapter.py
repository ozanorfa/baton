"""Contract tests: CodexAdapter vs recorded real CLI outputs (codex-cli 0.144.1)."""

from pathlib import Path

from ai_orchestrator.core.models import AgentRequest
from ai_orchestrator.providers.codex import CodexAdapter
from ai_orchestrator.transport.base import TransportResult

adapter = CodexAdapter(command="codex")


def raw(stdout: str, exit_code: int = 0, **kw) -> TransportResult:
    return TransportResult(exit_code=exit_code, stdout=stdout, stderr="", duration_s=1.0, **kw)


def request(**kw) -> AgentRequest:
    defaults = dict(role="planner", prompt="plan it", workdir=Path("/tmp/p"), timeout_s=600)
    return AgentRequest(**{**defaults, **kw})


def test_success_fixture(fixture_text) -> None:
    result = adapter.parse(raw(fixture_text("codex", "success.jsonl")))
    assert result.success
    assert result.text == "OK"
    assert result.session_id == "019f5051-c4a0-7642-b9e8-ea88db0f0c0c"
    assert result.usage.input_tokens == 12843
    assert result.usage.output_tokens == 5
    assert result.usage.cost_usd is None  # codex reports tokens, not cost — never fabricate


def test_error_fixture_collects_messages(fixture_text) -> None:
    result = adapter.parse(raw(fixture_text("codex", "error.jsonl"), exit_code=1))
    assert not result.success
    assert "no-such-model-xyz" in result.error
    assert result.session_id is not None  # thread started before the failure


def test_malformed_output_fails_without_raising(fixture_text) -> None:
    result = adapter.parse(raw(fixture_text("codex", "malformed.jsonl")))
    assert not result.success
    assert "unparseable" in result.error


def test_build_invocation_readonly_sandbox_for_readonly_roles() -> None:
    inv = adapter.build_invocation(request())
    assert inv.argv[:2] == ["codex", "exec"]
    assert inv.argv[inv.argv.index("-s") + 1] == "read-only"
    assert "--json" in inv.argv and "--skip-git-repo-check" in inv.argv
    assert inv.argv[-1] == "-"  # prompt via stdin
    assert inv.stdin == "plan it"


def test_build_invocation_write_sandbox_when_role_edits() -> None:
    inv = adapter.build_invocation(request(allow_edits=True))
    assert inv.argv[inv.argv.index("-s") + 1] == "workspace-write"


def test_build_invocation_resume_subcommand() -> None:
    inv = adapter.build_invocation(request(session_id="thread-42"))
    assert inv.argv[1:4] == ["exec", "resume", "thread-42"]
