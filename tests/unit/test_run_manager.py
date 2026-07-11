import json
from pathlib import Path

import pytest

from ai_orchestrator.core.models import RunState, StageSpec, StageStatus, utcnow
from ai_orchestrator.core.run_manager import RunManager

SPECS = [
    StageSpec(name="planner", role="planner", output="plan"),
    StageSpec(name="coder", role="coder", inputs=["plan"], output="code_changes"),
]


@pytest.fixture()
def manager(tmp_path: Path) -> RunManager:
    return RunManager(tmp_path)


def test_create_transition_reload(manager: RunManager) -> None:
    state = manager.create_run("add feature X", SPECS)

    run_dir = manager.run_dir(state.run_id)
    assert (run_dir / "run.json").is_file()
    for sub in ("artifacts", "prompts", "logs"):
        assert (run_dir / sub).is_dir()

    stage = state.stage("planner")
    stage.status = StageStatus.RUNNING
    stage.started_at = utcnow()
    manager.save(state)

    reloaded = manager.load_run(state.run_id)
    assert reloaded == state
    assert reloaded.stage("planner").status is StageStatus.RUNNING
    assert reloaded.stage("coder").status is StageStatus.PENDING


def test_crash_between_write_and_rename_keeps_previous_state(
    manager: RunManager, monkeypatch
) -> None:
    state = manager.create_run("req", SPECS)
    state.stage("planner").status = StageStatus.SUCCEEDED

    def boom(src, dst):  # simulated crash at the rename boundary
        raise OSError("simulated crash")

    monkeypatch.setattr("ai_orchestrator.core.run_manager.os.replace", boom)
    with pytest.raises(OSError, match="simulated crash"):
        manager.save(state)
    monkeypatch.undo()

    reloaded = manager.load_run(state.run_id)  # previous consistent state intact
    assert reloaded.stage("planner").status is StageStatus.PENDING
    json.loads((manager.run_dir(state.run_id) / "run.json").read_text())  # not corrupted


def test_artifacts_and_prompts(manager: RunManager) -> None:
    state = manager.create_run("req", SPECS)
    manager.save_artifact(state, "plan.md", "# Plan\n1. do it\n")
    assert manager.load_artifact(state, "plan.md") == "# Plan\n1. do it\n"

    prompt_path = manager.save_prompt(state, 1, "planner", "you are the planner")
    assert prompt_path.name == "01-planner.md"
    assert prompt_path.read_text() == "you are the planner"


def test_list_and_load_missing(manager: RunManager) -> None:
    assert manager.list_run_ids() == []
    a = manager.create_run("one", SPECS)
    b = manager.create_run("two", SPECS)
    assert set(manager.list_run_ids()) == {a.run_id, b.run_id}
    assert a.run_id != b.run_id
    with pytest.raises(FileNotFoundError, match="nope"):
        manager.load_run("nope")


def test_run_state_stage_names_match_specs(manager: RunManager) -> None:
    state = manager.create_run("req", SPECS)
    assert [s.name for s in state.stages] == ["planner", "coder"]
    assert isinstance(state, RunState)
