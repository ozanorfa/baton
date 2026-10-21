from pathlib import Path

import pytest

from ai_orchestrator.core.engine import PipelineEngine
from ai_orchestrator.core.models import (
    AgentResult,
    Capabilities,
    Health,
    RunStatus,
    StageSpec,
    StageStatus,
    Usage,
)
from ai_orchestrator.core.routing import ResolvedStage
from ai_orchestrator.core.run_manager import RunManager
from ai_orchestrator.observability.events import EventLog
from ai_orchestrator.providers.base import ProviderAdapter
from ai_orchestrator.transport.base import Invocation, TransportResult


class ScriptedAdapter(ProviderAdapter):
    """Mock adapter: yields pre-scripted AgentResults per stage role."""

    name = "scripted"
    capabilities = Capabilities()

    def __init__(self, script: dict[str, AgentResult]):
        super().__init__(command="scripted-bin")
        self.script = script

    def health_check(self, transport) -> Health:
        return Health(ok=True)

    def build_invocation(self, request) -> Invocation:
        return Invocation(
            argv=["scripted-bin", request.role],  # role smuggled for the fake transport
            stdin=request.prompt,
            workdir=request.workdir,
            timeout_s=request.timeout_s,
        )

    def parse(self, raw: TransportResult) -> AgentResult:
        return self.script[raw.stdout]


class RoleEchoTransport:
    """Fake transport: echoes the role back so parse() can look up its script."""

    def run(self, invocation: Invocation, on_line=None) -> TransportResult:
        return TransportResult(
            exit_code=0, stdout=invocation.argv[1], stderr="", duration_s=0.01
        )


def stage(name: str, adapter, *, inputs=(), output=None, enabled=True) -> ResolvedStage:
    return ResolvedStage(
        spec=StageSpec(
            name=name, role=name, optional=not enabled,
            inputs=list(inputs), output=output or f"{name}.md",
        ),
        provider_name="scripted",
        adapter=adapter,
        timeout_s=60,
        enabled=enabled,
        allow_edits=(name == "coder"),
    )


@pytest.fixture()
def manager(tmp_path: Path) -> RunManager:
    return RunManager(tmp_path)


def test_happy_path_two_stages(manager: RunManager) -> None:
    adapter = ScriptedAdapter(
        {
            "planner": AgentResult(success=True, text="THE PLAN", usage=Usage(input_tokens=10)),
            "coder": AgentResult(success=True, text="THE CHANGES", session_id="s-9"),
        }
    )
    stages = [
        stage("planner", adapter, output="plan.md"),
        stage("coder", adapter, inputs=["plan.md"], output="changes.md"),
    ]
    state = PipelineEngine(manager, RoleEchoTransport()).execute("add feature", stages)

    assert state.status is RunStatus.SUCCEEDED
    assert state.stage("planner").status is StageStatus.SUCCEEDED
    assert state.stage("coder").session_id == "s-9"
    assert manager.load_artifact(state, "plan.md") == "THE PLAN"
    assert manager.load_artifact(state, "changes.md") == "THE CHANGES"
    # the coder's prompt embeds the planner's artifact (naive M2 builder)
    prompt = (manager.run_dir(state.run_id) / "prompts" / "02-coder.md").read_text(encoding="utf-8")
    assert "THE PLAN" in prompt and "add feature" in prompt
    # reloaded state matches persisted state
    assert manager.load_run(state.run_id) == state


def test_optional_disabled_stage_is_skipped(manager: RunManager) -> None:
    adapter = ScriptedAdapter(
        {
            "planner": AgentResult(success=True, text="P"),
            "reviewer": AgentResult(success=True, text="R"),
        }
    )
    stages = [
        stage("planner", adapter),
        stage("designer", adapter, enabled=False),
        stage("reviewer", adapter),
    ]
    state = PipelineEngine(manager, RoleEchoTransport()).execute("req", stages)

    assert state.status is RunStatus.SUCCEEDED
    assert state.stage("designer").status is StageStatus.SKIPPED
    assert not (manager.artifacts_dir(state.run_id) / "designer.md").exists()


def test_mid_pipeline_failure_fail_stops(manager: RunManager) -> None:
    adapter = ScriptedAdapter(
        {
            "planner": AgentResult(success=True, text="P"),
            "coder": AgentResult(success=False, error="exit 1: kaboom"),
            "reviewer": AgentResult(success=True, text="never reached"),
        }
    )
    stages = [
        stage("planner", adapter),
        stage("coder", adapter),
        stage("reviewer", adapter),
    ]
    state = PipelineEngine(manager, RoleEchoTransport()).execute("req", stages)

    assert state.status is RunStatus.FAILED
    assert state.stage("coder").status is StageStatus.FAILED
    assert state.stage("coder").error == "exit 1: kaboom"
    assert state.stage("reviewer").status is StageStatus.PENDING  # later stages untouched
    assert manager.load_artifact(state, "planner.md") == "P"  # earlier artifacts preserved

    event_names = [e["event"] for e in EventLog(manager.logs_dir(state.run_id)).read()]
    assert event_names == [
        "run_started",
        "stage_started", "provider_invoked", "stage_succeeded",
        "stage_started", "provider_invoked", "stage_failed",
        "run_finished",
    ]


def test_raw_output_persisted_per_stage(manager: RunManager) -> None:
    adapter = ScriptedAdapter({"planner": AgentResult(success=True, text="P")})
    state = PipelineEngine(manager, RoleEchoTransport()).execute("req", [stage("planner", adapter)])
    stdout_file = manager.logs_dir(state.run_id) / "01-planner.stdout"
    assert stdout_file.read_text(encoding="utf-8") == "planner"  # raw transport output, pre-parse
