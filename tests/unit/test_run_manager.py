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


# ── ADR-027: generated artifacts never reach the reviewer as "coder changes" ──

def _repo(tmp_path):
    import subprocess
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "app.py").write_text("x = 1\n")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "seed"],
        cwd=tmp_path, check=True,
    )
    return tmp_path


def test_snapshot_ignores_generated_artifacts(tmp_path):
    """A stray __pycache__ must not read as work the coder did (ADR-027).

    Live finding 2026-07-28: `batonai review` returned NEEDS WORK citing .pyc
    files nobody authored, in a project whose .gitignore did not list them.
    """
    from ai_orchestrator.core.workspace import snapshot_changes

    project = _repo(tmp_path)
    (project / "__pycache__").mkdir()
    (project / "__pycache__" / "app.cpython-312.pyc").write_bytes(b"\x00compiled")
    (project / "node_modules").mkdir()
    (project / "node_modules" / "dep.js").write_text("module.exports = 1\n")

    snap = snapshot_changes(project)
    assert snap is not None
    assert snap.changed is False, "generated-only noise is not a workspace change"


def test_snapshot_still_sees_real_edits_alongside_noise(tmp_path):
    """The exclusion must not swallow genuine work happening in the same run."""
    from ai_orchestrator.core.workspace import snapshot_changes

    project = _repo(tmp_path)
    (project / "__pycache__").mkdir()
    (project / "__pycache__" / "app.cpython-312.pyc").write_bytes(b"\x00compiled")
    (project / "app.py").write_text("x = 2  # real edit\n")
    (project / "feature.py").write_text("def feature(): ...\n")  # real new file

    snap = snapshot_changes(project)
    assert snap is not None and snap.changed is True
    assert "real edit" in snap.patch
    assert "feature.py" in snap.patch
    assert ".pyc" not in snap.patch, "noise must not reach the reviewer"


def test_snapshot_keeps_directories_that_only_look_generated(tmp_path):
    """`build/` is real source in some projects — it is deliberately NOT excluded."""
    from ai_orchestrator.core.workspace import snapshot_changes

    project = _repo(tmp_path)
    (project / "build").mkdir()
    (project / "build" / "make.py").write_text("def build(): ...\n")

    snap = snapshot_changes(project)
    assert snap is not None and snap.changed is True
    assert "build/make.py" in snap.patch
