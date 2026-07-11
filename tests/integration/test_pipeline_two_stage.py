"""T19: full two-stage pipeline through the REAL stack — config loader,
routing, engine, headless transport, subprocess fake CLI. No mocks, no tokens.
"""

import json
from pathlib import Path

from ai_orchestrator.config.loader import load_config
from ai_orchestrator.core.engine import PipelineEngine
from ai_orchestrator.core.models import RunStatus, StageStatus
from ai_orchestrator.core.routing import RoutingEngine, build_stage_specs
from ai_orchestrator.core.run_manager import RunManager
from ai_orchestrator.observability.events import EventLog
from ai_orchestrator.transport.headless import HeadlessTransport


def run_pipeline(project: Path, registry, request: str):
    loaded = load_config(project, env={})
    transport = HeadlessTransport()
    specs = build_stage_specs(loaded.config)
    resolved = RoutingEngine(loaded.config, registry).resolve(specs, transport)
    manager = RunManager(project)
    state = PipelineEngine(manager, transport).execute(request, resolved)
    return state, manager


def test_two_stage_run_end_to_end(fake_project, fake_registry) -> None:
    state, manager = run_pipeline(fake_project, fake_registry, "add a login screen")

    assert state.status is RunStatus.SUCCEEDED
    run_dir = manager.run_dir(state.run_id)

    # run-dir layout (ARCHITECTURE §2.4)
    assert (run_dir / "run.json").is_file()
    assert (run_dir / "artifacts" / "plan.md").is_file()
    assert (run_dir / "artifacts" / "changes.md").is_file()
    assert (run_dir / "prompts" / "01-planner.md").is_file()
    assert (run_dir / "prompts" / "02-coder.md").is_file()
    assert (run_dir / "logs" / "01-planner.stdout").is_file()

    # artifact content flowed planner → coder
    plan = (run_dir / "artifacts" / "plan.md").read_text()
    assert plan.startswith("FAKE RESPONSE")
    coder_prompt = (run_dir / "prompts" / "02-coder.md").read_text()
    assert plan.strip() in coder_prompt  # coder received the plan artifact

    # run.json is valid and consistent
    data = json.loads((run_dir / "run.json").read_text())
    assert data["status"] == "succeeded"
    assert [s["status"] for s in data["stages"]] == ["succeeded", "succeeded"]

    # event stream shape
    names = [e["event"] for e in EventLog(run_dir / "logs").read()]
    assert names == [
        "run_started",
        "stage_started", "provider_invoked", "stage_succeeded",
        "stage_started", "provider_invoked", "stage_succeeded",
        "run_finished",
    ]


def test_two_stage_run_failure_variant(fake_project, fake_registry) -> None:
    # the request carries a directive the fake CLI acts on in stage 1
    state, manager = run_pipeline(
        fake_project, fake_registry, "do things [[fail:planner exploded]]"
    )

    assert state.status is RunStatus.FAILED
    assert state.stage("planner").status is StageStatus.FAILED
    assert "planner exploded" in state.stage("planner").error
    assert state.stage("coder").status is StageStatus.PENDING

    run_dir = manager.run_dir(state.run_id)
    assert not (run_dir / "artifacts" / "plan.md").exists()
    assert (run_dir / "prompts" / "01-planner.md").is_file()  # prompt preserved for debugging
    events = EventLog(run_dir / "logs").read()
    assert events[-2]["event"] == "stage_failed"
    assert events[-1] == {**events[-1], "event": "run_finished", "status": "failed"}
