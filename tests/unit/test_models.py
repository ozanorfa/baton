from pathlib import Path

import pytest
from pydantic import ValidationError

from ai_orchestrator.core.models import (
    RunState,
    StageResult,
    StageSpec,
    StageStatus,
    Usage,
    utcnow,
)


def make_run() -> RunState:
    return RunState(
        run_id="2026-07-11_1432_a3f9",
        request="Add Face ID support",
        project_dir=Path("/tmp/proj"),
        stages=[
            StageResult(name="planner", role="planner"),
            StageResult(name="coder", role="coder"),
        ],
    )


def test_runstate_json_round_trip() -> None:
    run = make_run()
    run.stage("planner").status = StageStatus.SUCCEEDED
    run.stage("planner").usage = Usage(input_tokens=100, output_tokens=50)

    restored = RunState.model_validate_json(run.model_dump_json())

    assert restored == run
    assert restored.stage("planner").usage.input_tokens == 100
    assert restored.stage("coder").status is StageStatus.PENDING


def test_invalid_status_rejected() -> None:
    with pytest.raises(ValidationError):
        StageResult(name="planner", role="planner", status="bogus")


def test_stage_spec_is_frozen() -> None:
    spec = StageSpec(name="coder", role="coder", inputs=["plan"], output="code_changes")
    with pytest.raises(ValidationError):
        spec.name = "other"


def test_duration_requires_both_timestamps() -> None:
    stage = StageResult(name="planner", role="planner")
    assert stage.duration_s is None
    stage.started_at = utcnow()
    assert stage.duration_s is None
    stage.finished_at = stage.started_at
    assert stage.duration_s == 0.0


def test_unknown_stage_lookup_raises() -> None:
    with pytest.raises(KeyError):
        make_run().stage("reviewer")
