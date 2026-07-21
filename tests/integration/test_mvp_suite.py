"""T29: the MVP end-to-end suite — full five-stage pipeline through the real
CLI on the fake provider. Report correctness, verdict parsing, and a failure
at every stage position. Zero tokens, fully deterministic.
"""

import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ai_orchestrator.cli.app import app

FAKE_CLI = Path(__file__).parent / "fake_provider" / "fake_ai.py"
runner = CliRunner()

STAGES = ["planner", "designer", "coder", "reviewer", "publisher"]


@pytest.fixture()
def mvp_project(tmp_path: Path, monkeypatch) -> Path:
    """Git repo, all five stages enabled, all roles on the fake provider."""
    project = tmp_path / "proj"
    (project / ".ai").mkdir(parents=True)
    (project / ".ai" / "config.yaml").write_text(
        "pipeline:\n  stages: [planner, designer, coder, reviewer, publisher]\n"
        "roles:\n"
        "  planner: {provider: fake}\n"
        "  designer: {provider: fake, enabled: true}\n"
        "  coder: {provider: fake}\n"
        "  reviewer: {provider: fake}\n"
        "  publisher: {provider: fake, enabled: true}\n"
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
    monkeypatch.chdir(project)
    return project


def run_dir_of(project: Path) -> Path:
    return next((project / ".ai" / "runs").iterdir())


HAPPY_REQUEST = (
    "add feature "
    "[[write@coder:feature.py:VALUE = 42]] "
    "[[output@reviewer:**Verdict** — APPROVE. Findings: None.]] "
    "[[output@publisher:Commit message: feat: add feature]]"
)


def test_full_pipeline_report_correctness(mvp_project, fake_registry) -> None:
    result = runner.invoke(app, ["run", HAPPY_REQUEST], env={"COLUMNS": "220"})
    assert result.exit_code == 0

    run_dir = run_dir_of(mvp_project)
    report = json.loads((run_dir / "report.json").read_text())

    assert report["status"] == "succeeded"
    assert report["verdict"] == "APPROVE"
    assert [s["name"] for s in report["stages"]] == STAGES
    assert all(s["status"] == "succeeded" for s in report["stages"])
    assert report["wall_duration_s"] >= 0
    # fake provider reports no usage → nulls, never zeros (risk R2)
    assert report["total_input_tokens"] is None
    assert report["total_cost_usd"] is None
    assert all(s["input_tokens"] is None for s in report["stages"])

    # all five artifacts + the coder's diff
    artifacts = run_dir / "artifacts"
    expected = ("plan.md", "design.md", "changes.md", "review.md", "diff.patch",
                "commit_message.md")
    for name in expected:
        assert (artifacts / name).is_file(), name
    assert "VALUE = 42" in (artifacts / "diff.patch").read_text()
    assert (mvp_project / "feature.py").is_file()

    # publisher never touches git (ADR-014: prepare-only) — still just the
    # fixture's one "init" commit, despite the coder having written a file
    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=mvp_project, capture_output=True, text=True
    )
    assert len(log.stdout.strip().splitlines()) == 1

    # terminal shows the verdict
    assert "APPROVE" in result.output


@pytest.mark.parametrize("victim", STAGES)
def test_failure_at_each_stage_position(mvp_project, fake_registry, victim) -> None:
    request = f"{HAPPY_REQUEST} [[fail@{victim}:{victim} exploded]]"
    result = runner.invoke(app, ["run", request], env={"COLUMNS": "220"})
    assert result.exit_code == 1

    report = json.loads((run_dir_of(mvp_project) / "report.json").read_text())
    assert report["status"] == "failed"

    stage_status = {s["name"]: s["status"] for s in report["stages"]}
    victim_index = STAGES.index(victim)
    for i, name in enumerate(STAGES):
        if i < victim_index:
            assert stage_status[name] == "succeeded", name
        elif i == victim_index:
            assert stage_status[name] == "failed"
            assert f"{victim} exploded" in report["stages"][i]["error"]
        else:
            assert stage_status[name] == "pending", name  # fail-stop: never reached

    assert f"{victim} exploded" in result.output  # failure guidance names the cause
    reviewer_index = STAGES.index("reviewer")
    if victim_index <= reviewer_index:
        assert report["verdict"] is None  # reviewer never completed
    else:
        assert report["verdict"] == "APPROVE"  # reviewer succeeded before the later failure
