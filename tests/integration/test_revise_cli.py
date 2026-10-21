"""ADR-019: `batonai revise` through the real CLI on the fake provider — continues
the same run with a correction, re-running from the coder."""

import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ai_orchestrator.cli.app import app

FAKE_CLI = Path(__file__).parent / "fake_provider" / "fake_ai.py"
runner = CliRunner()


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
        f"  fake: {{command: {FAKE_CLI}, timeout_s: 30}}\n", encoding="utf-8")
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


APPROVE = "[[output@reviewer:**Verdict** — APPROVE]]"


def test_revise_continues_same_run_with_correction(project, fake_registry) -> None:
    first = runner.invoke(
        app, ["run", f"build [[write@coder:app.py:x=1]] {APPROVE}"], env={"COLUMNS": "220"}
    )
    assert first.exit_code == 0
    run_id = only_run_id(project)
    assert (project / "app.py").read_text(encoding="utf-8") == "x=1\n"

    revised = runner.invoke(
        app,
        ["revise", f"set x to two [[write@coder:app.py:x=2]] {APPROVE}"],
        env={"COLUMNS": "220"},
    )
    assert revised.exit_code == 0
    assert f"revising {run_id}" in revised.output

    # same run — no second run directory was created
    assert len(list((project / ".ai" / "runs").iterdir())) == 1

    state = json.loads((project / ".ai" / "runs" / run_id / "run.json").read_text(encoding="utf-8"))
    assert state["status"] == "succeeded"
    assert "set x to two" in state["request"]  # correction injected into the request

    coder_prompt = (project / ".ai" / "runs" / run_id / "prompts" / "02-coder.md").read_text(
        encoding="utf-8"
    )
    assert "set x to two" in coder_prompt  # reached the coder
    assert (project / "app.py").read_text(
        encoding="utf-8"
    ) == "x=2\n"  # coder's revised write applied


def test_revise_with_no_runs_errors(project, fake_registry) -> None:
    # fresh project, no runs yet
    result = runner.invoke(app, ["revise", "fix it"])
    assert result.exit_code == 2
    assert "no runs to revise" in result.output


def test_revise_from_planner_reruns_whole_pipeline(project, fake_registry) -> None:
    first = runner.invoke(
        app, ["run", f"build [[write@coder:app.py:x=1]] {APPROVE}"], env={"COLUMNS": "220"}
    )
    assert first.exit_code == 0
    run_id = only_run_id(project)
    planner_before = json.loads(
        (project / ".ai" / "runs" / run_id / "run.json").read_text(encoding="utf-8")
    )["stages"][0]["started_at"]

    revised = runner.invoke(
        app,
        ["revise", "--from", "planner", f"rethink it [[write@coder:app.py:x=9]] {APPROVE}"],
        env={"COLUMNS": "220"},
    )
    assert revised.exit_code == 0
    planner_after = json.loads(
        (project / ".ai" / "runs" / run_id / "run.json").read_text(encoding="utf-8")
    )["stages"][0]["started_at"]
    assert planner_after != planner_before  # planner was re-run this time
