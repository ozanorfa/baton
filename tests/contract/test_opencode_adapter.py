"""Contract tests: OpencodeAdapter vs recorded real CLI outputs (opencode 1.18.4)."""

from pathlib import Path

from ai_orchestrator.core.models import AgentRequest
from ai_orchestrator.providers.opencode import OpencodeAdapter
from ai_orchestrator.transport.base import TransportResult

adapter = OpencodeAdapter(command="opencode")


def request(**kw) -> AgentRequest:
    defaults = dict(role="publisher", prompt="draft it", workdir=Path("/tmp/p"), timeout_s=600)
    return AgentRequest(**{**defaults, **kw})


def test_success_fixture(fixture_text) -> None:
    raw = TransportResult(
        exit_code=0, stdout=fixture_text("opencode", "success.txt"), stderr="", duration_s=8.0
    )
    result = adapter.parse(raw)
    assert result.success
    assert result.text == "OK"
    assert result.usage is None  # no tokens on stdout in run mode — honest None
    assert result.session_id is None  # session id unreachable in default format


def test_error_fixture(fixture_text) -> None:
    raw = TransportResult(
        exit_code=1, stdout="", stderr=fixture_text("opencode", "error_stderr.txt"),
        duration_s=2.0,
    )
    result = adapter.parse(raw)
    assert not result.success
    assert "UnknownError" in result.error


def test_timeout_passthrough() -> None:
    raw = TransportResult(
        exit_code=None, stdout="", stderr="", duration_s=600.0, timed_out=True,
        error="timed out after 600s",
    )
    result = adapter.parse(raw)
    assert not result.success
    assert "timed out" in result.error


def test_build_invocation_prompt_after_separator_not_stdin() -> None:
    inv = adapter.build_invocation(request())
    assert inv.argv[0] == "opencode"
    assert inv.argv[1] == "run"
    # `--` stops option parsing; the prompt is the trailing positional (ADR-010 exception)
    assert inv.argv[-2] == "--"
    assert inv.argv[-1] == "draft it"
    assert inv.stdin == ""
    assert "--auto" not in inv.argv  # never auto-approve tools (shallow-text-only)
    assert "--share" not in inv.argv  # never upload the session publicly


def test_build_invocation_dash_leading_prompt_is_not_a_flag() -> None:
    inv = adapter.build_invocation(request(prompt="-x looks like a flag"))
    assert inv.argv[inv.argv.index("--") + 1] == "-x looks like a flag"


def test_build_invocation_model_only_when_set() -> None:
    assert "--model" not in adapter.build_invocation(request()).argv
    inv = OpencodeAdapter(command="opencode", model="openrouter/free-model").build_invocation(
        request()
    )
    assert inv.argv[inv.argv.index("--model") + 1] == "openrouter/free-model"
