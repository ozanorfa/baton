"""T33+T34: batonai resume, timeout handling, Ctrl-C safety — through the real CLI
on the fake provider."""

import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ai_orchestrator.cli.app import app
from ai_orchestrator.core.engine import PipelineEngine
from ai_orchestrator.core.models import RunStatus, StageSpec, StageStatus
from ai_orchestrator.core.routing import ResolvedStage
from ai_orchestrator.core.run_manager import RunManager

FAKE_CLI = Path(__file__).parent / "fake_provider" / "fake_ai.py"
runner = CliRunner()

RESUMABLE_REQUEST = (
    "build it "
    "[[fail_once@coder:session limit hit]] "
    "[[write@coder:done.py:x = 1]] "
    "[[output@reviewer:**Verdict** — APPROVE]]"
)


@pytest.fixture()
def project(tmp_path: Path, monkeypatch) -> Path:
    proj = tmp_path / "proj"
    (proj / ".ai").mkdir(parents=True)
    (proj / ".ai" / "config.yaml").write_text(
        "pipeline:\n  stages: [planner, coder, reviewer]\n"
        "roles:\n"
        "  planner: {provider: fake}\n"
        "  coder: {provider: fake}\n"
        "  reviewer: {provider: fake}\n"
        "providers:\n"
        f"  fake: {{command: {FAKE_CLI}, timeout_s: 30}}\n"
    )
    subprocess.run(["git", "init", "-q"], cwd=proj, check=True)
    subprocess.run(["git", "add", "-A"], cwd=proj, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"],
        cwd=proj, check=True,
    )
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.chdir(proj)
    return proj


def only_run_id(project: Path) -> str:
    return next((project / ".ai" / "runs").iterdir()).name


def test_resume_continues_from_failed_stage(project, fake_registry) -> None:
    first = runner.invoke(app, ["run", RESUMABLE_REQUEST], env={"COLUMNS": "220"})
    assert first.exit_code == 1
    run_id = only_run_id(project)
    assert f"batonai resume {run_id}" in first.output  # failure UX advertises resume

    state_before = json.loads((project / ".ai" / "runs" / run_id / "run.json").read_text())
    planner_before = state_before["stages"][0]
    assert planner_before["status"] == "succeeded"

    resumed = runner.invoke(app, ["resume", run_id], env={"COLUMNS": "220"})
    assert resumed.exit_code == 0
    assert "resuming:" in resumed.output
    assert "APPROVE" in resumed.output

    state_after = json.loads((project / ".ai" / "runs" / run_id / "run.json").read_text())
    assert state_after["status"] == "succeeded"
    # planner untouched: same record, not re-run (token waste = zero)
    assert state_after["stages"][0]["started_at"] == planner_before["started_at"]
    assert (project / "done.py").is_file()  # coder's second attempt did the work

    # coder's resumed prompt reused the planner artifact loaded from disk
    coder_prompt = (project / ".ai" / "runs" / run_id / "prompts" / "02-coder.md").read_text()
    plan = (project / ".ai" / "runs" / run_id / "artifacts" / "plan.md").read_text()
    assert plan.strip() in coder_prompt

    report = json.loads((project / ".ai" / "runs" / run_id / "report.json").read_text())
    assert report["status"] == "succeeded" and report["verdict"] == "APPROVE"


def test_resume_of_succeeded_run_refused(project, fake_registry) -> None:
    ok = runner.invoke(
        app,
        ["run", "fine [[write@coder:a.py:pass]] [[output@reviewer:**Verdict** — APPROVE]]"],
    )
    assert ok.exit_code == 0
    result = runner.invoke(app, ["resume", only_run_id(project)])
    assert result.exit_code == 2
    assert "nothing to resume" in result.output


def test_resume_from_flag_redoes_stage(project, fake_registry) -> None:
    ok = runner.invoke(
        app,
        ["run", "fine [[write@coder:a.py:pass]] [[output@reviewer:**Verdict** — APPROVE]]"],
    )
    assert ok.exit_code == 0
    run_id = only_run_id(project)
    redo = runner.invoke(app, ["resume", run_id, "--from", "reviewer"], env={"COLUMNS": "220"})
    assert redo.exit_code == 0
    state = json.loads((project / ".ai" / "runs" / run_id / "run.json").read_text())
    assert state["status"] == "succeeded"


def test_resume_refused_when_config_changed(project, fake_registry) -> None:
    failed = runner.invoke(app, ["run", "x [[fail@coder:dead]]"])
    assert failed.exit_code == 1
    run_id = only_run_id(project)
    config = project / ".ai" / "config.yaml"
    config.write_text(config.read_text().replace("[planner, coder, reviewer]", "[planner, coder]"))
    result = runner.invoke(app, ["resume", run_id])
    assert result.exit_code == 2
    assert "configuration changed" in result.output


def test_resume_unknown_run_id_exit_2(project, fake_registry) -> None:
    assert runner.invoke(app, ["resume", "no-such-run"]).exit_code == 2


def test_resume_with_designer_keeps_stage_enabled(project, fake_registry) -> None:
    """Audit gap (2026-07-12): resuming a --with-designer run without the flag
    silently dropped the designer. The flag must survive into resume."""
    config = project / ".ai" / "config.yaml"
    text = config.read_text()
    text = text.replace("[planner, coder, reviewer]", "[planner, designer, coder, reviewer]")
    text = text.replace(
        "  coder: {provider: fake}",
        "  designer: {provider: fake}\n  coder: {provider: fake}",
    )
    config.write_text(text)

    request = (
        "build [[fail_once@coder:limit]] [[write@coder:ok.py:x=1]] "
        "[[output@reviewer:**Verdict** — APPROVE]]"
    )
    first = runner.invoke(app, ["run", "--with-designer", request], env={"COLUMNS": "220"})
    assert first.exit_code == 1  # coder failed once; designer already succeeded
    run_id = only_run_id(project)

    resumed = runner.invoke(
        app, ["resume", run_id, "--with-designer"], env={"COLUMNS": "220"}
    )
    assert resumed.exit_code == 0
    state = json.loads((project / ".ai" / "runs" / run_id / "run.json").read_text())
    designer = next(s for s in state["stages"] if s["name"] == "designer")
    assert designer["status"] == "succeeded"  # kept, not silently skipped
    # coder's resumed prompt still received the design artifact from disk
    coder_prompt = (project / ".ai" / "runs" / run_id / "prompts" / "03-coder.md").read_text()
    design = (project / ".ai" / "runs" / run_id / "artifacts" / "design.md").read_text()
    assert design.strip() in coder_prompt


def test_timeout_becomes_clean_stage_failure(project, fake_registry) -> None:
    config = project / ".ai" / "config.yaml"
    config.write_text(config.read_text().replace("timeout_s: 30", "timeout_s: 1"))
    result = runner.invoke(app, ["run", "slow [[sleep@coder:5]]"], env={"COLUMNS": "220"})
    assert result.exit_code == 1
    assert "timed out after 1s" in result.output
    state = json.loads((project / ".ai" / "runs" / only_run_id(project) / "run.json").read_text())
    assert state["stages"][1]["status"] == "failed"


def test_coder_declared_no_op_succeeds(project, fake_registry) -> None:
    """ADR-021: a coder that changes nothing but declares no_changes_needed is a
    valid outcome, not the silent permission-block failure."""
    request = (
        "add a license header if missing "
        "[[output@coder:CHANGE_STATUS: no_changes_needed — header already present]] "
        "[[output@reviewer:**Verdict** — APPROVE]]"
    )
    result = runner.invoke(app, ["run", request], env={"COLUMNS": "220"})
    assert result.exit_code == 0
    run_id = only_run_id(project)
    state = json.loads((project / ".ai" / "runs" / run_id / "run.json").read_text())
    coder = next(s for s in state["stages"] if s["name"] == "coder")
    assert coder["status"] == "succeeded"  # no-op accepted, not failed
    # nothing changed → no diff.patch artifact
    assert not (project / ".ai" / "runs" / run_id / "artifacts" / "diff.patch").exists()


def test_coder_silent_no_change_still_fails(project, fake_registry) -> None:
    """Safety net preserved (ADR-007): zero change WITHOUT the marker still fails,
    so a silent permission block is never mistaken for a success."""
    request = "do something real [[output@coder:I did nothing and forgot the marker]]"
    result = runner.invoke(app, ["run", request], env={"COLUMNS": "220"})
    assert result.exit_code == 1
    run_id = only_run_id(project)
    state = json.loads((project / ".ai" / "runs" / run_id / "run.json").read_text())
    coder = next(s for s in state["stages"] if s["name"] == "coder")
    assert coder["status"] == "failed"
    assert "no workspace changes" in coder["error"]


class InterruptingTransport:
    def run(self, invocation, on_line=None):
        raise KeyboardInterrupt


def test_ctrl_c_leaves_resumable_state(tmp_path: Path) -> None:
    from ai_orchestrator.core.models import Capabilities

    class NullAdapter:
        name = "null"
        capabilities = Capabilities()

        def build_invocation(self, request):
            return None

        def parse(self, raw):
            raise AssertionError("never reached")

    manager = RunManager(tmp_path)
    spec = StageSpec(name="planner", role="planner", output="plan.md")
    stage = ResolvedStage(
        spec=spec, provider_name="null", adapter=NullAdapter(),
        timeout_s=5, enabled=True, allow_edits=False,
    )
    engine = PipelineEngine(manager, InterruptingTransport())
    with pytest.raises(KeyboardInterrupt):
        engine.execute("req", [stage])

    state = manager.load_run(manager.list_run_ids()[0])
    assert state.status is RunStatus.FAILED  # persisted before propagating
    assert state.stage("planner").status is StageStatus.FAILED
    assert "batonai resume" in state.stage("planner").error
