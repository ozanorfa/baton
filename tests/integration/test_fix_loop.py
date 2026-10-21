"""ADR-023: fix-loop — one automatic fix pass on a NEEDS WORK verdict, opt-in.

The revise machinery itself is covered by ADR-019's tests; here we check only
the *trigger* logic (fires once on NEEDS WORK when enabled, never otherwise)
via the `run_revised` event in the run's JSONL log.
"""

import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ai_orchestrator.cli.app import app

FAKE_CLI = Path(__file__).parent / "fake_provider" / "fake_ai.py"
runner = CliRunner()

# `append`, not `write`: the fix pass must change the tree again, or the engine
# (correctly, ADR-034) treats an identical tree as a silent no-op and fails it.
NEEDS_WORK = (
    "build it [[append@coder:app.py:x=1]] [[output@reviewer:**Verdict** — NEEDS WORK]]"
)
APPROVE = (
    "build it [[write@coder:app.py:x=1]] [[output@reviewer:**Verdict** — APPROVE]]"
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


def _revised_count(project: Path, run_id: str) -> int:
    log = project / ".ai" / "runs" / run_id / "logs" / "orchestrator.jsonl"
    return sum(
        1
        for line in log.read_text(encoding="utf-8").splitlines()
        if line and json.loads(line)["event"] == "run_revised"
    )


def test_fix_loop_fires_exactly_once_on_needs_work(project, fake_registry) -> None:
    result = runner.invoke(app, ["run", "--fix-loop", NEEDS_WORK], env={"COLUMNS": "220"})
    assert result.exit_code == 0
    run_id = only_run_id(project)
    # exactly one fix pass — never a second loop even though the verdict stays NEEDS WORK
    assert _revised_count(project, run_id) == 1
    # the review findings reached the re-run coder
    coder_prompt = (project / ".ai" / "runs" / run_id / "prompts" / "02-coder.md").read_text(
        encoding="utf-8"
    )
    assert "Address them, then stop" in coder_prompt
    assert len(list((project / ".ai" / "runs").iterdir())) == 1  # same run — revise reuses it


def test_no_fix_loop_without_the_flag(project, fake_registry) -> None:
    result = runner.invoke(app, ["run", NEEDS_WORK], env={"COLUMNS": "220"})
    assert result.exit_code == 0
    run_id = only_run_id(project)
    assert _revised_count(project, run_id) == 0  # opt-in: no flag, no loop


def test_no_fix_loop_on_clean_approve(project, fake_registry) -> None:
    result = runner.invoke(app, ["run", "--fix-loop", APPROVE], env={"COLUMNS": "220"})
    assert result.exit_code == 0
    run_id = only_run_id(project)
    assert _revised_count(project, run_id) == 0  # APPROVE is clean — nothing to fix


def test_fix_loop_via_project_config(project, fake_registry) -> None:
    config = project / ".ai" / "config.yaml"
    config.write_text(config.read_text(encoding="utf-8").replace(
        "pipeline:\n  stages:", "pipeline:\n  fix_loop: true\n  stages:"
    ))
    result = runner.invoke(app, ["run", NEEDS_WORK], env={"COLUMNS": "220"})
    assert result.exit_code == 0
    assert _revised_count(project, only_run_id(project)) == 1  # config enables it, no flag needed
