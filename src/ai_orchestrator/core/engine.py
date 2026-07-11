"""The pipeline engine (ARCHITECTURE.md §2.2) — deliberately boring.

A sequential interpreter over a static stage list. MVP semantics: no retries,
no escalation, no parallelism, no reordering (ADR-004, ADR-008). Every state
transition is persisted before the next action (ADR-005), so a crash at any
point leaves an inspectable, resumable run directory.
"""

from collections.abc import Callable

from ai_orchestrator.core.models import (
    AgentRequest,
    RunState,
    RunStatus,
    StageStatus,
    utcnow,
)
from ai_orchestrator.core.routing import ResolvedStage
from ai_orchestrator.core.run_manager import RunManager
from ai_orchestrator.observability import events as ev
from ai_orchestrator.observability.events import EventLog
from ai_orchestrator.transport.base import Transport

PromptBuilder = Callable[[ResolvedStage, str, dict[str, str]], str]


def naive_prompt_builder(stage: ResolvedStage, request: str, artifacts: dict[str, str]) -> str:
    """M2 stub: request + inlined input artifacts. Replaced by the layered
    ContextManager in M3 (T23) — do not grow logic here."""
    parts = [f"You are the {stage.spec.role}.", "", f"## Request\n{request}"]
    for name in stage.spec.inputs:
        if name in artifacts:
            parts.append(f"## Input: {name}\n{artifacts[name]}")
    return "\n\n".join(parts)


class PipelineEngine:
    def __init__(
        self,
        run_manager: RunManager,
        transport: Transport,
        prompt_builder: PromptBuilder = naive_prompt_builder,
    ):
        self.run_manager = run_manager
        self.transport = transport
        self.prompt_builder = prompt_builder

    def execute(self, request: str, resolved: list[ResolvedStage]) -> RunState:
        state = self.run_manager.create_run(request, [r.spec for r in resolved])
        log = EventLog(self.run_manager.logs_dir(state.run_id))
        log.emit(ev.RUN_STARTED, run_id=state.run_id, request=request)

        artifacts: dict[str, str] = {}
        failed = False

        for position, stage in enumerate(resolved, start=1):
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

            prompt = self.prompt_builder(stage, request, artifacts)
            self.run_manager.save_prompt(state, position, stage.spec.name, prompt)

            agent_request = AgentRequest(
                role=stage.spec.role,
                prompt=prompt,
                workdir=self.run_manager.project_dir,
                timeout_s=stage.timeout_s,
                allow_edits=stage.allow_edits,
            )
            log.emit(
                ev.PROVIDER_INVOKED,
                stage=stage.spec.name,
                provider=stage.provider_name,
                timeout_s=stage.timeout_s,
                allow_edits=stage.allow_edits,
            )
            raw = self.transport.run(stage.adapter.build_invocation(agent_request))

            # Persist raw output before evaluating anything (ARCHITECTURE §2.2).
            logs_dir = self.run_manager.logs_dir(state.run_id)
            stdout_path = logs_dir / f"{position:02d}-{stage.spec.name}.stdout"
            stdout_path.write_text(raw.stdout)
            (logs_dir / f"{position:02d}-{stage.spec.name}.stderr").write_text(raw.stderr)

            result = stage.adapter.parse(raw)
            record.finished_at = utcnow()
            record.session_id = result.session_id
            record.usage = result.usage

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
