"""ADR-014: the optional Publisher stage — off by default, per-project and
per-provider opt-in, prepare-only (never touches git)."""

import subprocess
from pathlib import Path

from typer.testing import CliRunner

from ai_orchestrator.cli.app import app

FAKE_CLI = Path(__file__).parent / "fake_provider" / "fake_ai.py"
runner = CliRunner()


def git_project(tmp_path: Path, monkeypatch, config: str) -> Path:
    project = tmp_path / "proj"
    (project / ".ai").mkdir(parents=True)
    (project / ".ai" / "config.yaml").write_text(config, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    subprocess.run(["git", "add", "-A"], cwd=project, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"],
        cwd=project, check=True,
    )
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.chdir(project)
    return project


BASE_CONFIG = (
    "pipeline:\n  stages: [planner, coder, reviewer, publisher]\n"
    "roles:\n"
    "  planner: {{provider: fake}}\n"
    "  coder: {{provider: fake}}\n"
    "  reviewer: {{provider: fake}}\n"
    "  publisher: {{provider: fake{publisher_extra}}}\n"
    "providers:\n"
    f"  fake: {{{{command: {FAKE_CLI}, timeout_s: 30}}}}\n"
)

REQUEST = (
    "add feature [[write@coder:x.py:pass]] "
    "[[output@reviewer:**Verdict** — APPROVE]] "
    "[[output@publisher:Commit message: feat: add x]]"
)


def test_publisher_skipped_by_default(tmp_path, fake_registry, monkeypatch) -> None:
    project = git_project(tmp_path, monkeypatch, BASE_CONFIG.format(publisher_extra=""))
    result = runner.invoke(app, ["run", REQUEST], env={"COLUMNS": "220"})
    assert result.exit_code == 0
    assert "publisher skipped" in result.output
    run_dir = next((project / ".ai" / "runs").iterdir())
    assert not (run_dir / "artifacts" / "commit_message.md").exists()


def test_with_publisher_flag_enables_stage_and_drafts_only(
    tmp_path, fake_registry, monkeypatch
) -> None:
    project = git_project(tmp_path, monkeypatch, BASE_CONFIG.format(publisher_extra=""))
    result = runner.invoke(
        app, ["run", "--with-publisher", REQUEST], env={"COLUMNS": "220"}
    )
    assert result.exit_code == 0
    assert "✓ publisher" in result.output

    run_dir = next((project / ".ai" / "runs").iterdir())
    draft = run_dir / "artifacts" / "commit_message.md"
    assert draft.is_file()
    assert "feat: add x" in draft.read_text(encoding="utf-8")

    # ADR-014: prepare-only — still exactly the fixture's one commit
    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=project, capture_output=True, text=True
    )
    assert len(log.stdout.strip().splitlines()) == 1
    # nothing staged or committed by the stage either
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=project, capture_output=True, text=True
    )
    assert "x.py" in status.stdout  # coder's file is there...
    assert not status.stdout.startswith("A ")  # ...but untracked/unstaged, not added


def test_publisher_can_use_a_different_provider_than_coder(
    tmp_path, fake_registry, monkeypatch
) -> None:
    """The exact scenario that motivated ADR-014: guarantee a specific
    provider handles publish-drafting, independent of who wrote the code."""
    config = (
        "pipeline:\n  stages: [planner, coder, reviewer, publisher]\n"
        "roles:\n"
        "  planner: {provider: fake}\n"
        "  coder: {provider: fake}\n"
        "  reviewer: {provider: fake}\n"
        "  publisher: {provider: fake_alt}\n"
        "providers:\n"
        f"  fake: {{command: {FAKE_CLI}, timeout_s: 30}}\n"
        f"  fake_alt: {{command: {FAKE_CLI}, timeout_s: 30}}\n"
    )
    project = git_project(tmp_path, monkeypatch, config)
    result = runner.invoke(
        app, ["run", "--with-publisher", REQUEST], env={"COLUMNS": "220"}
    )
    assert result.exit_code == 0
    run_dir = next((project / ".ai" / "runs").iterdir())
    import json

    state = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    providers = {s["name"]: s["provider"] for s in state["stages"]}
    assert providers["coder"] == "fake"
    assert providers["publisher"] == "fake_alt"  # deterministically different, guaranteed
