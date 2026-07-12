"""The pipeline engine (ARCHITECTURE.md §2.2) — deliberately boring.

A sequential interpreter over a static stage list. MVP semantics: no retries,
no escalation, no parallelism, no reordering (ADR-004, ADR-008). Every state
transition is persisted before the next action (ADR-005), so a crash at any
point leaves an inspectable, resumable run directory.

Session chaining (ADR-015): when two stages share a provider (e.g. Planner
and Reviewer both Codex by default), the later one resumes the earlier one's
session instead of cold-starting, cutting redundant repo re-exploration.
Never crosses providers — that's a hard vendor boundary, not a choice.
"""

from collections.abc import Callable

from ai_orchestrator.core.models import (
    AgentRequest,
    RunState,
    RunStatus,
    StageResult,
    StageSpec,
    StageStatus,
    utcnow,
)
from ai_orchestrator.core.routing import ResolvedStage
from ai_orchestrator.core.run_manager import RunManager
from ai_orchestrator.core.workspace import snapshot_changes
from ai_orchestrator.observability import events as ev
from ai_orchestrator.observability.events import EventLog
from ai_orchestrator.transport.base import Transport

PromptBuilder = Callable[[StageSpec, str, dict[str, str]], str]


class ResumeError(Exception):
    """Resume is impossible or ambiguous; message says why."""


def naive_prompt_builder(spec: StageSpec, request: str, artifacts: dict[str, str]) -> str:
    """Bare-bones fallback (used by unit tests). Production wiring passes
    ContextManager.build (context/manager.py) — the layered system."""
    parts = [f"You are the {spec.role}.", "", f"## Request\n{request}"]
    for name in spec.inputs:
        if name in artifacts:
            parts.append(f"## Input: {name}\n{artifacts[name]}")
    return "\n\n".join(parts)


class PipelineEngine:
    def __init__(
        self,
        run_manager: RunManager,
        transport: Transport,
        prompt_builder: PromptBuilder = naive_prompt_builder,
        event_sink: Callable[[dict], None] | None = None,
        session_chaining: bool = True,
    ):
        self.run_manager = run_manager
        self.transport = transport
        self.prompt_builder = prompt_builder
        self.event_sink = event_sink
        self.session_chaining = session_chaining

    def execute(self, request: str, resolved: list[ResolvedStage]) -> RunState:
        state = self.run_manager.create_run(request, [r.spec for r in resolved])
        log = EventLog(self.run_manager.logs_dir(state.run_id), sink=self.event_sink)
        log.emit(ev.RUN_STARTED, run_id=state.run_id, request=request)
        return self._run(state, resolved, artifacts={}, start=0, log=log)

    def resume(
        self, state: RunState, resolved: list[ResolvedStage], from_stage: str | None = None
    ) -> RunState:
        """Continue a run from its failed stage (or `from_stage`), reusing all
        artifacts already on disk (ADR-005: resume falls out of the file layout)."""
        names = [r.spec.name for r in resolved]
        if from_stage is not None:
            if from_stage not in names:
                raise ResumeError(f"unknown stage {from_stage!r}; stages: {names}")
            start = names.index(from_stage)
        else:
            start = next(
                (
                    i
                    for i, s in enumerate(state.stages)
                    if s.status not in (StageStatus.SUCCEEDED, StageStatus.SKIPPED)
                ),
                None,
            )
            if start is None:
                raise ResumeError(
                    f"run {state.run_id} completed successfully — nothing to resume "
                    "(use --from <stage> to deliberately redo a stage)"
                )

        for i in range(start, len(state.stages)):
            old = state.stages[i]
            state.stages[i] = StageResult(name=old.name, role=old.role)
        state.status = RunStatus.RUNNING
        self.run_manager.save(state)

        artifacts: dict[str, str] = {}
        artifacts_dir = self.run_manager.artifacts_dir(state.run_id)
        for path in sorted(artifacts_dir.iterdir()) if artifacts_dir.is_dir() else []:
            if path.is_file():
                artifacts[path.name] = path.read_text()

        log = EventLog(self.run_manager.logs_dir(state.run_id), sink=self.event_sink)
        log.emit(
            ev.RUN_RESUMED,
            run_id=state.run_id,
            from_stage=state.stages[start].name,
            reused_artifacts=sorted(artifacts),
        )
        return self._run(state, resolved, artifacts=artifacts, start=start, log=log)

    def _run(
        self,
        state: RunState,
        resolved: list[ResolvedStage],
        artifacts: dict[str, str],
        start: int,
        log: EventLog,
    ) -> RunState:
        request = state.request
        failed = False

        # Seed the per-provider session chain from stages already completed
        # in a prior attempt (resume), keyed by the provider each historically
        # used — not by stage adjacency, so Planner -> Coder -> Reviewer still
        # chains Reviewer to Planner's session when both are the same provider.
        #
        # Each entry also records the allow_edits it was created with: some
        # providers fix sandbox/write-access at session-creation time and
        # reject changing it on resume (verified: `codex exec resume` errors
        # on `-s/--sandbox`). Chaining into a stage with different write
        # needs would silently keep the OLD access level, so we only chain
        # when allow_edits matches — never a silent capability change.
        provider_sessions: dict[str, tuple[str, bool]] = {}
        specs_by_name = {r.spec.name: r for r in resolved}
        for record_i in state.stages[:start]:
            succeeded = record_i.status is StageStatus.SUCCEEDED
            historical_stage = specs_by_name.get(record_i.name)
            if succeeded and record_i.provider and record_i.session_id and historical_stage:
                provider_sessions[record_i.provider] = (
                    record_i.session_id, historical_stage.allow_edits
                )

        for position, stage in enumerate(resolved, start=1):
            if position <= start:
                continue  # already succeeded/skipped in a previous attempt
            record = state.stage(stage.spec.name)

            if not stage.enabled:
                record.status = StageStatus.SKIPPED
                self.run_manager.save(state)
                log.emit(ev.STAGE_SKIPPED, stage=stage.spec.name, reason="disabled")
                continue

            record.status = StageStatus.RUNNING
            record.provider = stage.provider_name
            record.started_at = utcnow()
            self.run_manager.save(state)
            log.emit(ev.STAGE_STARTED, stage=stage.spec.name, provider=stage.provider_name)

            prompt = self.prompt_builder(stage.spec, request, artifacts)
            self.run_manager.save_prompt(state, position, stage.spec.name, prompt)

            resume_session_id = None
            if self.session_chaining and stage.adapter.capabilities.supports_resume:
                prior = provider_sessions.get(stage.provider_name)
                if prior is not None and prior[1] == stage.allow_edits:
                    resume_session_id = prior[0]

            agent_request = AgentRequest(
                role=stage.spec.role,
                prompt=prompt,
                workdir=self.run_manager.project_dir,
                timeout_s=stage.timeout_s,
                allow_edits=stage.allow_edits,
                session_id=resume_session_id,
            )
            log.emit(
                ev.PROVIDER_INVOKED,
                stage=stage.spec.name,
                provider=stage.provider_name,
                timeout_s=stage.timeout_s,
                allow_edits=stage.allow_edits,
                resumed_session=resume_session_id,
            )
            try:
                raw = self.transport.run(stage.adapter.build_invocation(agent_request))
            except KeyboardInterrupt:
                # Ctrl-C must leave a resumable run, not a corrupt one (T34).
                record.status = StageStatus.FAILED
                record.finished_at = utcnow()
                record.error = (
                    f"interrupted by user (Ctrl-C); continue with: ai resume {state.run_id}"
                )
                state.status = RunStatus.FAILED
                self.run_manager.save(state)
                log.emit(ev.STAGE_FAILED, stage=stage.spec.name, error=record.error)
                log.emit(ev.RUN_FINISHED, run_id=state.run_id, status=state.status)
                raise

            # Persist raw output before evaluating anything (ARCHITECTURE §2.2).
            logs_dir = self.run_manager.logs_dir(state.run_id)
            stdout_path = logs_dir / f"{position:02d}-{stage.spec.name}.stdout"
            stdout_path.write_text(raw.stdout)
            (logs_dir / f"{position:02d}-{stage.spec.name}.stderr").write_text(raw.stderr)

            result = stage.adapter.parse(raw)
            record.finished_at = utcnow()
            record.session_id = result.session_id
            record.usage = result.usage
            if result.success and result.session_id:
                provider_sessions[stage.provider_name] = (result.session_id, stage.allow_edits)

            if not result.success:
                record.status = StageStatus.FAILED
                record.error = result.error or "unknown failure"
                state.status = RunStatus.FAILED
                self.run_manager.save(state)
                log.emit(
                    ev.STAGE_FAILED,
                    stage=stage.spec.name,
                    error=record.error,
                    raw_stdout=str(stdout_path),
                    duration_s=record.duration_s,
                )
                failed = True
                break  # fail-stop: log, preserve, halt (ADR-008)

            self.run_manager.save_artifact(state, stage.spec.output, result.text)
            artifacts[stage.spec.output] = result.text
            record.artifact = stage.spec.output

            if stage.allow_edits:
                snapshot = snapshot_changes(self.run_manager.project_dir)
                if snapshot is not None and not snapshot.changed:
                    # Protocol said success but nothing changed — the silent
                    # permission-block signature (ADR-007; claude fixture
                    # permission_block.json). Only the workspace can tell.
                    record.status = StageStatus.FAILED
                    record.error = (
                        f"{stage.spec.name!r} reported success but no workspace changes "
                        "were detected. Likely causes: a permission block inside the "
                        "provider, or the stage decided no changes were needed. Inspect "
                        f"its output artifact ({stage.spec.output}) and raw logs."
                    )
                    state.status = RunStatus.FAILED
                    self.run_manager.save(state)
                    log.emit(ev.STAGE_FAILED, stage=stage.spec.name, error=record.error)
                    failed = True
                    break
                if snapshot is not None and snapshot.patch:
                    self.run_manager.save_artifact(state, "diff.patch", snapshot.patch)
                    artifacts["diff.patch"] = snapshot.patch

            record.status = StageStatus.SUCCEEDED
            self.run_manager.save(state)
            log.emit(
                ev.STAGE_SUCCEEDED,
                stage=stage.spec.name,
                artifact=stage.spec.output,
                duration_s=record.duration_s,
            )

        if not failed:
            state.status = RunStatus.SUCCEEDED
            self.run_manager.save(state)
        log.emit(ev.RUN_FINISHED, run_id=state.run_id, status=state.status)
        return state
