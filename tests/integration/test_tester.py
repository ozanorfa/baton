"""ADR-024: the Tester stage — zero-LLM, runs the project's tests, report-and-continue."""

import json
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from ai_orchestrator.cli.app import app

FAKE_CLI = Path(__file__).parent / "fake_provider" / "fake_ai.py"
runner = CliRunner()

REQUEST = "build it [[write@coder:app.py:x=1]] [[output@reviewer:**Verdict** — APPROVE]]"


def make_project(tmp_path: Path, monkeypatch, test_command: str) -> Path:
    proj = tmp_path / "proj"
    (proj / ".ai").mkdir(parents=True)
    (proj / ".ai" / "config.yaml").write_text(
        "pipeline:\n  stages: [planner, coder, tester, reviewer]\n"
        "roles:\n"
        "  planner: {provider: fake}\n"
        "  coder: {provider: fake}\n"
        "  tester: {provider: testrunner, enabled: false}\n"
        "  reviewer: {provider: fake}\n"
        "providers:\n"
        f"  fake: {{command: {FAKE_CLI}, timeout_s: 30}}\n"
        f'  testrunner: {{command: "{test_command}", timeout_s: 30}}\n', encoding="utf-8")
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


def _stage(project: Path, run_id: str, name: str) -> dict:
    state = json.loads((project / ".ai" / "runs" / run_id / "run.json").read_text(encoding="utf-8"))
    return next(s for s in state["stages"] if s["name"] == name)


def test_passing_tests_report_and_succeed(tmp_path, monkeypatch, fake_registry) -> None:
    project = make_project(tmp_path, monkeypatch, "true")  # exit 0
    result = runner.invoke(app, ["run", "--with-tester", REQUEST], env={"COLUMNS": "220"})
    assert result.exit_code == 0
    run_id = only_run_id(project)
    report = (project / ".ai" / "runs" / run_id / "artifacts" / "test_report.md").read_text(encoding="utf-8")
    assert "PASSED" in report
    assert _stage(project, run_id, "tester")["status"] == "succeeded"


def test_failing_tests_still_succeed_and_reach_reviewer(
    tmp_path, monkeypatch, fake_registry
) -> None:
    project = make_project(tmp_path, monkeypatch, "false")  # exit 1
    result = runner.invoke(app, ["run", "--with-tester", REQUEST], env={"COLUMNS": "220"})
    assert result.exit_code == 0  # report-and-continue: no fail-stop
    run_id = only_run_id(project)
    report = (project / ".ai" / "runs" / run_id / "artifacts" / "test_report.md").read_text(encoding="utf-8")
    assert "FAILED" in report
    assert _stage(project, run_id, "tester")["status"] == "succeeded"  # tester itself succeeded
    # the reviewer received the test report as an admitted input
    reviewer_prompt = (project / ".ai" / "runs" / run_id / "prompts" / "04-reviewer.md").read_text(encoding="utf-8")
    assert "Test report" in reviewer_prompt and "FAILED" in reviewer_prompt


def test_tester_skipped_without_the_flag(tmp_path, monkeypatch, fake_registry) -> None:
    project = make_project(tmp_path, monkeypatch, "true")
    result = runner.invoke(app, ["run", REQUEST], env={"COLUMNS": "220"})
    assert result.exit_code == 0
    run_id = only_run_id(project)
    assert _stage(project, run_id, "tester")["status"] == "skipped"
    assert not (project / ".ai" / "runs" / run_id / "artifacts" / "test_report.md").exists()
