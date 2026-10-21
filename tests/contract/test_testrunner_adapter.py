"""Contract tests: TestRunnerAdapter — the zero-LLM Tester (ADR-024)."""

from pathlib import Path

from ai_orchestrator.core.models import AgentRequest
from ai_orchestrator.providers.testrunner import (
    NOT_DETECTED,
    TestRunnerAdapter,
    detect_command,
)
from ai_orchestrator.transport.base import TransportResult


def request(workdir: Path, **kw) -> AgentRequest:
    defaults = dict(role="tester", prompt="(ignored)", workdir=workdir, timeout_s=600)
    return AgentRequest(**{**defaults, **kw})


def test_parse_passed_when_tests_exit_zero() -> None:
    adapter = TestRunnerAdapter(command="pytest")
    raw = TransportResult(exit_code=0, stdout="5 passed", stderr="", duration_s=1.0)
    result = adapter.parse(raw)
    assert result.success
    assert "PASSED" in result.text and "5 passed" in result.text
    assert result.usage is None  # zero-LLM → no tokens


def test_parse_failed_result_is_still_a_successful_stage() -> None:
    """Report-and-continue (ADR-024): failing tests are a valid report, not a
    stage failure — the Reviewer decides what to do with it."""
    adapter = TestRunnerAdapter(command="pytest")
    raw = TransportResult(exit_code=1, stdout="1 failed", stderr="AssertionError", duration_s=1.0)
    result = adapter.parse(raw)
    assert result.success  # the stage succeeded — the tests ran
    assert "FAILED" in result.text and "exit code 1" in result.text
    assert "AssertionError" in result.text


def test_parse_no_command_detected_fails_the_stage() -> None:
    adapter = TestRunnerAdapter(command="auto")
    raw = TransportResult(
        exit_code=None, stdout="", stderr="", duration_s=0.0,
        error=f"binary not found: {NOT_DETECTED}",
    )
    result = adapter.parse(raw)
    assert not result.success
    assert "no test command detected" in result.error


def test_parse_timeout_fails_the_stage() -> None:
    adapter = TestRunnerAdapter(command="pytest")
    raw = TransportResult(
        exit_code=None, stdout="", stderr="", duration_s=600.0, timed_out=True,
        error="timed out after 600s",
    )
    result = adapter.parse(raw)
    assert not result.success
    assert "timed out" in result.error


def test_build_invocation_explicit_command_is_shlex_split(tmp_path) -> None:
    adapter = TestRunnerAdapter(command="uv run pytest -q")
    inv = adapter.build_invocation(request(tmp_path))
    assert inv.argv == ["uv", "run", "pytest", "-q"]


def test_build_invocation_auto_detects_from_marker(tmp_path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    inv = TestRunnerAdapter(command="auto").build_invocation(request(tmp_path))
    assert inv.argv == ["pytest"]


def test_build_invocation_auto_with_no_marker_is_sentinel(tmp_path) -> None:
    inv = TestRunnerAdapter(command="auto").build_invocation(request(tmp_path))
    assert inv.argv == [NOT_DETECTED]


def test_detect_command_priority(tmp_path) -> None:
    assert detect_command(tmp_path) is None
    (tmp_path / "go.mod").write_text("module x\n", encoding="utf-8")
    assert detect_command(tmp_path) == "go test ./..."
    (tmp_path / "package.json").write_text("{}\n", encoding="utf-8")
    # package.json sits ahead of go.mod in the priority list
    assert detect_command(tmp_path) == "npm test"
