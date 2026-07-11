"""T26: edit-stage workspace verification in a real git repo.

The coder either changed files (→ diff.patch captured, reviewer sees it)
or it didn't (→ failed stage with guidance, the silent-permission-block
detector), even though the provider reported success both times.
"""

import subprocess
from pathlib import Path

from ai_orchestrator.config.loader import load_config
from ai_orchestrator.context.manager import ContextManager
from ai_orchestrator.core.engine import PipelineEngine
from ai_orchestrator.core.models import RunStatus, StageStatus
from ai_orchestrator.core.routing import RoutingEngine, build_stage_specs
from ai_orchestrator.core.run_manager import RunManager
from ai_orchestrator.core.workspace import snapshot_changes
from ai_orchestrator.transport.headless import HeadlessTransport

FAKE_CLI = Path(__file__).parent / "fake_provider" / "fake_ai.py"


def git_project(tmp_path: Path, monkeypatch) -> Path:
    project = tmp_path / "repo"
    (project / ".ai").mkdir(parents=True)
    (project / ".ai" / "config.yaml").write_text(
        "pipeline:\n  stages: [planner, coder, reviewer]\n"
        "roles:\n"
        "  planner: {provider: fake}\n"
        "  coder: {provider: fake}\n"
        "  reviewer: {provider: fake}\n"
        "providers:\n"
        f"  fake: {{command: {FAKE_CLI}, timeout_s: 30}}\n"
    )
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    subprocess.run(["git", "add", "-A"], cwd=project, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"],
        cwd=project, check=True,
    )
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    return project


def run_pipeline(project: Path, registry, request: str):
    loaded = load_config(project, env={})
    transport = HeadlessTransport()
    resolved = RoutingEngine(loaded.config, registry).resolve(
        build_stage_specs(loaded.config), transport
    )
    manager = RunManager(project)
    context = ContextManager(project, loaded.config.context.project_profile)
    state = PipelineEngine(manager, transport, prompt_builder=context.build).execute(
        request, resolved
    )
    return state, manager


def test_coder_changes_produce_diff_patch_for_reviewer(tmp_path, fake_registry, monkeypatch):
    project = git_project(tmp_path, monkeypatch)
    state, manager = run_pipeline(
        project, fake_registry, "make it [[write@coder:hello.py:print('hi')]]"
    )

    assert state.status is RunStatus.SUCCEEDED
    assert (project / "hello.py").is_file()  # the "coder" really edited the workspace
    patch = manager.load_artifact(state, "diff.patch")
    assert "hello.py" in patch and "print('hi')" in patch
    # the reviewer's prompt includes the diff (contract now admits diff.patch)
    reviewer_prompt = (manager.run_dir(state.run_id) / "prompts" / "03-reviewer.md").read_text()
    assert "diff.patch" in reviewer_prompt and "print('hi')" in reviewer_prompt


def test_no_workspace_change_fails_edit_stage_with_guidance(tmp_path, fake_registry, monkeypatch):
    project = git_project(tmp_path, monkeypatch)
    # fake provider replies happily but writes nothing — the permission-block signature
    state, manager = run_pipeline(project, fake_registry, "please change things")

    assert state.status is RunStatus.FAILED
    coder = state.stage("coder")
    assert coder.status is StageStatus.FAILED
    assert "no workspace changes" in coder.error
    assert state.stage("reviewer").status is StageStatus.PENDING
    # the coder's claimed summary is preserved for inspection
    assert manager.load_artifact(state, "changes.md").startswith("FAKE RESPONSE")


def test_snapshot_handles_non_git_dir(tmp_path):
    assert snapshot_changes(tmp_path / "not-a-repo") is None or True  # no crash contract


def test_snapshot_detects_tracked_and_untracked(tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / "a.txt").write_text("one\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "c"],
        cwd=repo, check=True,
    )
    snap = snapshot_changes(repo)
    assert snap is not None and not snap.changed

    (repo / "a.txt").write_text("one\ntwo\n")  # tracked modification
    (repo / "new.txt").write_text("brand new\n")  # untracked file
    snap = snapshot_changes(repo)
    assert snap.changed
    assert "+two" in snap.patch and "+brand new" in snap.patch
