"""Contract tests: AntigravityAdapter vs recorded real CLI outputs (agy 1.1.1)."""

from pathlib import Path

from ai_orchestrator.core.models import AgentRequest
from ai_orchestrator.providers.antigravity import AntigravityAdapter
from ai_orchestrator.transport.base import TransportResult

adapter = AntigravityAdapter(command="agy")


def request(**kw) -> AgentRequest:
    defaults = dict(role="designer", prompt="design it", workdir=Path("/tmp/p"), timeout_s=600)
    return AgentRequest(**{**defaults, **kw})


def test_success_fixture(fixture_text) -> None:
    raw = TransportResult(
        exit_code=0, stdout=fixture_text("antigravity", "success.txt"), stderr="", duration_s=8.0
    )
    result = adapter.parse(raw)
    assert result.success
    assert result.text == "OK"
    assert result.usage is None  # agy reports no tokens in print mode — honest None
    assert result.session_id is None  # conversation id unreachable headlessly


def test_error_fixture(fixture_text) -> None:
    raw = TransportResult(
        exit_code=1, stdout="", stderr=fixture_text("antigravity", "error_stderr.txt"),
        duration_s=2.0,
    )
    result = adapter.parse(raw)
    assert not result.success
    assert "Agent execution terminated" in result.error


def test_timeout_passthrough() -> None:
    raw = TransportResult(
        exit_code=None, stdout="", stderr="", duration_s=600.0, timed_out=True,
        error="timed out after 600s",
    )
    result = adapter.parse(raw)
    assert not result.success
    assert "timed out" in result.error


def test_build_invocation_prompt_in_argv_not_stdin() -> None:
    inv = adapter.build_invocation(request())
    assert inv.argv[0] == "agy"
    assert inv.argv[inv.argv.index("-p") + 1] == "design it"  # ADR-010 exception, documented
    assert inv.stdin == ""
    assert "--sandbox" not in inv.argv  # incompatible with print mode (verified agy 1.1.1)
    assert inv.argv[inv.argv.index("--print-timeout") + 1] == "600s"


def test_build_invocation_edit_mode_only_when_allowed() -> None:
    assert "--mode" not in adapter.build_invocation(request()).argv
    inv = adapter.build_invocation(request(allow_edits=True))
    assert inv.argv[inv.argv.index("--mode") + 1] == "accept-edits"
