"""Contract tests: ClaudeCodeAdapter vs recorded real CLI outputs (claude 2.1.207).

No subprocess runs here — parse() and build_invocation() are pure (T09).
"""

from pathlib import Path

from ai_orchestrator.core.models import AgentRequest
from ai_orchestrator.providers.claude import ClaudeCodeAdapter
from ai_orchestrator.transport.base import TransportResult

adapter = ClaudeCodeAdapter(command="claude")


def raw(stdout: str, exit_code: int = 0, **kw) -> TransportResult:
    return TransportResult(exit_code=exit_code, stdout=stdout, stderr="", duration_s=1.0, **kw)


def request(**kw) -> AgentRequest:
    defaults = dict(role="coder", prompt="do it", workdir=Path("/tmp/p"), timeout_s=900)
    return AgentRequest(**{**defaults, **kw})


def test_success_fixture(fixture_text) -> None:
    result = adapter.parse(raw(fixture_text("claude", "success.json")))
    assert result.success
    assert result.text == "OK"
    assert result.session_id == "eda3e354-365b-4e9a-8931-169d16c211b1"
    assert result.usage.output_tokens == 39
    assert result.usage.input_tokens == 9 + 6713 + 11347  # input + cache creation + cache read
    assert result.usage.cost_usd > 0


def test_error_fixture_is_failed_with_message(fixture_text) -> None:
    result = adapter.parse(raw(fixture_text("claude", "error.json"), exit_code=1))
    assert not result.success
    assert "no-such-model-xyz" in result.error
    assert result.session_id  # still recorded for diagnostics


def test_permission_block_is_undetectable_at_protocol_level(fixture_text) -> None:
    """Captured reality: blocked run exits 0, is_error=false, no work done.
    The adapter must NOT pretend to detect this — stage-level diff check does (T26)."""
    result = adapter.parse(raw(fixture_text("claude", "permission_block.json")))
    assert result.success  # honest: the protocol says success
    assert "Permission is required" in result.text


def test_malformed_output_fails_without_raising(fixture_text) -> None:
    result = adapter.parse(raw(fixture_text("claude", "malformed.json")))
    assert not result.success
    assert "unparseable" in result.error
    assert result.text  # raw text preserved for the run dir


def test_transport_failure_passthrough() -> None:
    result = adapter.parse(
        TransportResult(
            exit_code=None, stdout="", stderr="", duration_s=0.1, timed_out=True,
            error="timed out after 900s",
        )
    )
    assert not result.success
    assert "timed out" in result.error


def test_build_invocation_flags() -> None:
    inv = adapter.build_invocation(request(allow_edits=True, session_id="abc-123"))
    assert inv.argv[0] == "claude"
    assert "--output-format" in inv.argv and "json" in inv.argv
    assert inv.argv[inv.argv.index("--resume") + 1] == "abc-123"
    assert inv.argv[inv.argv.index("--permission-mode") + 1] == "acceptEdits"
    assert inv.stdin == "do it"  # prompt on stdin, never argv (ADR-010)
    assert "do it" not in inv.argv


def test_build_invocation_readonly_role_has_no_permission_flags() -> None:
    inv = adapter.build_invocation(request(role="planner", allow_edits=False))
    assert "--permission-mode" not in inv.argv
    assert "--resume" not in inv.argv


def test_model_flag_from_config() -> None:
    pinned = ClaudeCodeAdapter(command="claude", model="opus")
    inv = pinned.build_invocation(request())
    assert inv.argv[inv.argv.index("--model") + 1] == "opus"
