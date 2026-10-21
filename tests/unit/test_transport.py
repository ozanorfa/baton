import sys
from pathlib import Path

from ai_orchestrator.transport.base import Invocation
from ai_orchestrator.transport.headless import HeadlessTransport

transport = HeadlessTransport()


def invocation(argv: list[str], stdin: str = "", timeout_s: int = 10, **kw) -> Invocation:
    return Invocation(argv=argv, stdin=stdin, workdir=Path.cwd(), timeout_s=timeout_s, **kw)


def test_stdin_delivery_and_exit_code() -> None:
    cat = [sys.executable, "-c", "import sys; sys.stdout.write(sys.stdin.read())"]
    result = transport.run(invocation(cat, stdin="hello prompt\nline 2"))
    assert result.ok
    assert result.exit_code == 0
    assert result.stdout == "hello prompt\nline 2"
    assert result.duration_s > 0


def test_nonzero_exit_code_captured() -> None:
    result = transport.run(
        invocation([sys.executable, "-c", "import sys; sys.stderr.write('boom'); sys.exit(3)"])
    )
    assert not result.ok
    assert result.exit_code == 3
    assert result.stderr == "boom"
    assert not result.timed_out


def test_timeout_returns_structured_result() -> None:
    sleeper = [sys.executable, "-c", "import time; time.sleep(30)"]
    result = transport.run(invocation(sleeper, timeout_s=1))
    assert not result.ok
    assert result.timed_out
    assert result.exit_code is None
    assert "timed out after 1s" in (result.error or "")


def test_missing_binary_returns_structured_result() -> None:
    result = transport.run(invocation(["/nonexistent/binary-xyz"]))
    assert not result.ok
    assert result.exit_code is None
    assert "binary not found" in (result.error or "")


def test_env_additions_visible_to_child() -> None:
    result = transport.run(
        invocation(
            [sys.executable, "-c", "import os; print(os.environ['AI_ORCH_TEST_VAR'])"],
            env={"AI_ORCH_TEST_VAR": "42"},
        )
    )
    assert result.ok
    assert result.stdout.strip() == "42"
