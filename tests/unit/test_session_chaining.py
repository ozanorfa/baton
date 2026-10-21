"""ADR-015: same-provider session chaining in the pipeline engine.

Uses mock adapters (no subprocess) so the chaining *decision logic* — which
is entirely in core/engine.py — is tested in isolation from any real CLI.
"""

from pathlib import Path

import pytest

from ai_orchestrator.core.engine import PipelineEngine
from ai_orchestrator.core.models import (
    AgentRequest,
    AgentResult,
    Capabilities,
    Health,
    StageSpec,
    StageStatus,
)
from ai_orchestrator.core.routing import ResolvedStage
from ai_orchestrator.core.run_manager import RunManager
from ai_orchestrator.providers.base import ProviderAdapter
from ai_orchestrator.transport.base import Invocation, TransportResult


class RecordingAdapter(ProviderAdapter):
    """Records the session_id it was invoked with; returns scripted results
    keyed by call order. Two instances = two genuinely distinct providers."""

    capabilities = Capabilities(supports_resume=True)

    def __init__(self, name: str, results: list[AgentResult]):
        super().__init__(command=f"{name}-bin")
        self.name = name
        self.results = list(results)
        self.received_session_ids: list[str | None] = []
        self._call = 0

    def health_check(self, transport) -> Health:
        return Health(ok=True)

    def build_invocation(self, request: AgentRequest) -> Invocation:
        self.received_session_ids.append(request.session_id)
        return Invocation(
            argv=[self.command, str(self._call)],
            stdin=request.prompt, workdir=request.workdir, timeout_s=request.timeout_s,
        )

    def parse(self, raw: TransportResult) -> AgentResult:
        result = self.results[self._call]
        self._call += 1
        return result


class NoResumeAdapter(RecordingAdapter):
    capabilities = Capabilities(supports_resume=False)


class IndexEchoTransport:
    def run(self, invocation: Invocation, on_line=None) -> TransportResult:
        return TransportResult(exit_code=0, stdout=invocation.argv[1], stderr="", duration_s=0.01)


def make_stage(name: str, adapter: ProviderAdapter, *, allow_edits=False) -> ResolvedStage:
    return ResolvedStage(
        spec=StageSpec(name=name, role=name, output=f"{name}.md"),
        provider_name=adapter.name,
        adapter=adapter,
        timeout_s=60,
        enabled=True,
        allow_edits=allow_edits,
    )


@pytest.fixture()
def manager(tmp_path: Path) -> RunManager:
    return RunManager(tmp_path)


def test_second_stage_on_same_provider_resumes_first(manager) -> None:
    """Planner -> Reviewer, both 'codex' (ADR-015's actual default scenario)."""
    codex = RecordingAdapter(
        "codex",
        [
            AgentResult(success=True, text="PLAN", session_id="codex-session-1"),
            AgentResult(success=True, text="REVIEW", session_id="codex-session-2"),
        ],
    )
    stages = [make_stage("planner", codex), make_stage("reviewer", codex)]
    engine = PipelineEngine(manager, IndexEchoTransport())
    engine.execute("req", stages)

    assert codex.received_session_ids == [None, "codex-session-1"]  # 2nd resumes 1st


def test_different_providers_never_chain(manager) -> None:
    """Planner (codex) -> Coder (claude): a hard vendor boundary, not a choice."""
    codex = RecordingAdapter("codex", [AgentResult(success=True, text="PLAN", session_id="c-1")])
    claude = RecordingAdapter("claude", [AgentResult(success=True, text="CODE", session_id="a-1")])
    stages = [make_stage("planner", codex), make_stage("coder", claude, allow_edits=True)]
    engine = PipelineEngine(manager, IndexEchoTransport())
    engine.execute("req", stages)

    assert claude.received_session_ids == [None]  # never inherits codex's session


def test_intervening_different_provider_stage_does_not_break_the_chain(manager) -> None:
    """Planner(codex) -> Coder(claude) -> Reviewer(codex): Reviewer still
    chains to Planner despite Coder sitting between them (keyed by provider,
    not by adjacency) — the actual shape of the default 5-stage pipeline."""
    codex = RecordingAdapter(
        "codex",
        [
            AgentResult(success=True, text="PLAN", session_id="codex-1"),
            AgentResult(success=True, text="REVIEW", session_id="codex-2"),
        ],
    )
    claude = RecordingAdapter("claude", [AgentResult(success=True, text="CODE", session_id="a-1")])
    stages = [
        make_stage("planner", codex),
        make_stage("coder", claude, allow_edits=True),
        make_stage("reviewer", codex),
    ]
    engine = PipelineEngine(manager, IndexEchoTransport())
    engine.execute("req", stages)

    assert codex.received_session_ids == [None, "codex-1"]


def test_provider_without_resume_capability_never_chains(manager) -> None:
    agy = NoResumeAdapter(
        "antigravity",
        [
            AgentResult(success=True, text="A", session_id=None),  # agy never reports one anyway
            AgentResult(success=True, text="B", session_id=None),
        ],
    )
    stages = [make_stage("planner", agy), make_stage("designer", agy)]
    engine = PipelineEngine(manager, IndexEchoTransport())
    engine.execute("req", stages)

    assert agy.received_session_ids == [None, None]


def test_session_chaining_disabled_via_config_flag(manager) -> None:
    codex = RecordingAdapter(
        "codex",
        [
            AgentResult(success=True, text="PLAN", session_id="codex-1"),
            AgentResult(success=True, text="REVIEW", session_id="codex-2"),
        ],
    )
    stages = [make_stage("planner", codex), make_stage("reviewer", codex)]
    engine = PipelineEngine(manager, IndexEchoTransport(), session_chaining=False)
    engine.execute("req", stages)

    assert codex.received_session_ids == [None, None]  # opted out — always cold


def test_mismatched_allow_edits_never_chains(manager) -> None:
    """Field bug (2026-07-12): `codex exec resume` rejects -s/--sandbox — a
    resumed session keeps its original write-access level. Chaining a
    read-only stage's session into an edit-needing stage would silently
    keep it read-only, so the engine must refuse to chain across a
    read-only/write-access boundary, even on the same provider."""
    codex = RecordingAdapter(
        "codex",
        [
            AgentResult(success=True, text="PLAN", session_id="codex-1"),  # read-only
            AgentResult(success=True, text="CODE", session_id="codex-2"),  # needs write
        ],
    )
    stages = [
        make_stage("planner", codex, allow_edits=False),
        make_stage("coder", codex, allow_edits=True),
    ]
    engine = PipelineEngine(manager, IndexEchoTransport())
    engine.execute("req", stages)

    assert codex.received_session_ids == [None, None]  # never chained — access levels differ


def test_revise_coder_resumes_own_session_and_reviewer_resumes_its_own(manager) -> None:
    """ADR-019/ADR-034: after a full run, `revise` re-runs from the Coder. The
    Coder resumes its OWN prior session (the correction is the next turn), and
    so does the Reviewer — its own transcript already contains the Planner's
    (it was chained from it) plus what it flagged last time. Planner is not re-run."""
    codex = RecordingAdapter(
        "codex",
        [
            AgentResult(success=True, text="PLAN", session_id="codex-1"),
            AgentResult(success=True, text="REVIEW", session_id="codex-2"),
        ],
    )
    claude = RecordingAdapter(
        "claude", [AgentResult(success=True, text="CODE", session_id="claude-1")]
    )
    stages = [
        make_stage("planner", codex),
        make_stage("coder", claude, allow_edits=True),
        make_stage("reviewer", codex),
    ]
    engine = PipelineEngine(manager, IndexEchoTransport())
    state = engine.execute("req", stages)
    assert claude.received_session_ids == [None]
    assert codex.received_session_ids == [None, "codex-1"]

    codex.results.append(AgentResult(success=True, text="REVIEW2", session_id="codex-3"))
    claude.results.append(AgentResult(success=True, text="CODE2", session_id="claude-2"))
    engine.revise(state, stages, "make the button blue")

    # Coder re-ran resuming its OWN session; Reviewer resumed ITS OWN; Planner not re-run.
    assert claude.received_session_ids == [None, "claude-1"]
    assert codex.received_session_ids == [None, "codex-1", "codex-2"]


def test_revise_appends_correction_to_request(manager) -> None:
    """The correction is injected into the run's request so every re-run stage
    sees it (the Coder does not receive review.md by contract)."""
    codex = RecordingAdapter(
        "codex", [AgentResult(success=True, text="PLAN", session_id="codex-1")]
    )
    claude = RecordingAdapter(
        "claude", [AgentResult(success=True, text="CODE", session_id="claude-1")]
    )
    stages = [make_stage("planner", codex), make_stage("coder", claude, allow_edits=True)]
    engine = PipelineEngine(manager, IndexEchoTransport())
    state = engine.execute("build a thing", stages)

    claude.results.append(AgentResult(success=True, text="CODE2", session_id="claude-2"))
    state = engine.revise(state, stages, "use a dark theme")

    assert "build a thing" in state.request
    assert "use a dark theme" in state.request
    assert claude.received_session_ids == [None, "claude-1"]  # coder resumed itself


def test_resume_rebuilds_chain_from_succeeded_history(manager) -> None:
    """Planner succeeds (codex), Reviewer fails; on resume, Reviewer (also
    codex) must still resume Planner's session even though Planner isn't
    re-run this time — the chain has to survive a fail-stop/resume cycle."""
    codex = RecordingAdapter(
        "codex",
        [
            AgentResult(success=True, text="PLAN", session_id="codex-1"),
            AgentResult(success=False, error="boom"),  # first reviewer attempt fails
        ],
    )
    stages = [make_stage("planner", codex), make_stage("reviewer", codex)]
    engine = PipelineEngine(manager, IndexEchoTransport())
    state = engine.execute("req", stages)
    assert state.stage("reviewer").status is StageStatus.FAILED

    codex.results.append(AgentResult(success=True, text="REVIEW", session_id="codex-2"))
    engine.resume(state, stages)

    # calls: [0]=planner(None), [1]=reviewer-attempt-1(codex-1), [2]=reviewer-retry(codex-1)
    assert codex.received_session_ids == [None, "codex-1", "codex-1"]
