"""Zero-LLM Tester adapter: run the project's test command, report PASS/FAIL (ADR-024).

Like the `deterministic` publisher (ADR-018), this is a zero-token provider — it
ignores the prompt and delegates the one side effect (running the tests) to the
transport. The test command is **auto-detected** from stack marker files
(`pyproject.toml` → `pytest`, `package.json` → `npm test`, …) and overridable via
`providers: {testrunner: {command: "<your test command>"}}`.

Report-and-continue (ADR-024): running the tests and getting failures is still a
*successful test run*, so a FAILED result is a successful stage whose report says
FAILED — the Reviewer reads `test_report.md` and factors it into the verdict (a
failure → NEEDS WORK → fix-loop). Only a missing test command or a timeout fails
the stage itself.
"""

import os
import shlex
from pathlib import Path

from ai_orchestrator.core.models import AgentRequest, AgentResult, Capabilities, Health
from ai_orchestrator.providers.base import ProviderAdapter
from ai_orchestrator.providers.registry import registry
from ai_orchestrator.transport.base import Invocation, Transport, TransportResult

# Marker file → conventional test command. First match wins (priority order).
TEST_COMMANDS: list[tuple[str, str]] = [
    ("pyproject.toml", "pytest"),
    ("requirements.txt", "pytest"),
    ("package.json", "npm test"),
    ("go.mod", "go test ./..."),
    ("Cargo.toml", "cargo test"),
    ("pubspec.yaml", "flutter test"),
    ("Gemfile", "bundle exec rspec"),
    ("pom.xml", "mvn test"),
    ("build.gradle", "gradle test"),
]

# Sentinel argv used when no command is configured or detectable: the transport
# reports "binary not found", which parse() turns into a clear config message.
NOT_DETECTED = "__no_test_command__"
_OUTPUT_CAP = 4000  # keep the tail — test failures surface at the end


def detect_command(project_dir: Path) -> str | None:
    for marker, command in TEST_COMMANDS:
        if (project_dir / marker).exists():
            return command
    return None


def _resolve(command: str | None, project_dir: Path) -> str | None:
    if command and command.strip().lower() != "auto":
        return command
    return detect_command(project_dir)


@registry.register
class TestRunnerAdapter(ProviderAdapter):
    __test__ = False  # not a pytest test class despite the "Test" name prefix
    name = "testrunner"
    capabilities = Capabilities(supports_resume=False, reports_tokens=False, edits_files=False)

    def health_check(self, transport: Transport) -> Health:
        # The command resolves against the run's workdir, which isn't known here,
        # so we can't probe it up front — the real check happens when it runs.
        return Health(ok=True, binary=self.command, detail="test command resolved at runtime")

    def build_invocation(self, request: AgentRequest) -> Invocation:
        command = _resolve(self.command, request.workdir)
        # posix=False on Windows: a configured `C:\\tools\\pytest.exe -q` must keep
        # its backslashes instead of having them eaten as escapes (ADR-035).
        argv = shlex.split(command, posix=os.name != "nt") if command else [NOT_DETECTED]
        return Invocation(
            argv=argv,
            stdin="",
            workdir=request.workdir,
            timeout_s=request.timeout_s,
        )

    def parse(self, raw: TransportResult) -> AgentResult:
        if raw.timed_out:
            return AgentResult(success=False, error=raw.error, text=raw.stdout)
        if raw.error is not None:
            if NOT_DETECTED in raw.error:
                return AgentResult(
                    success=False,
                    error="no test command detected for this stack — set "
                    "providers.testrunner.command to your project's test command",
                )
            return AgentResult(success=False, error=raw.error, text=raw.stdout)

        output = (raw.stdout + ("\n" + raw.stderr if raw.stderr.strip() else "")).strip()
        tail = output[-_OUTPUT_CAP:] if len(output) > _OUTPUT_CAP else output
        if tail != output:
            tail = "… (truncated)\n" + tail
        # Report-and-continue: a FAILED result is still a successful test *run*.
        if raw.exit_code == 0:
            body = "**Result: PASSED** ✓"
        else:
            body = f"**Result: FAILED** ✗ (exit code {raw.exit_code})"
        return AgentResult(success=True, text=f"# Test report\n\n{body}\n\n```\n{tail}\n```")
