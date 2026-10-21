"""ADR-022: `batonai review` — sends the current working-tree diff to the Reviewer,
pipeline-free and read-only."""

import subprocess
from pathlib import Path

from typer.testing import CliRunner

from ai_orchestrator.cli.app import app

FAKE_CLI = Path(__file__).parent / "fake_provider" / "fake_ai.py"
runner = CliRunner()


def git_project(tmp_path: Path, monkeypatch) -> Path:
    proj = tmp_path / "proj"
    (proj / ".ai").mkdir(parents=True)
    (proj / ".ai" / "config.yaml").write_text(
        "pipeline:\n  stages: [reviewer]\n"
        "roles:\n  reviewer: {provider: fake}\n"
        "providers:\n"
        f"  fake: {{command: {FAKE_CLI}, timeout_s: 30}}\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=proj, check=True)
    (proj / "seed.txt").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=proj, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"],
        cwd=proj, check=True,
    )
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.chdir(proj)
    return proj


def _commits(project: Path) -> int:
    return int(
        subprocess.run(
            ["git", "rev-list", "--count", "HEAD"], cwd=project, capture_output=True, text=True
        ).stdout.strip()
    )


def test_review_prints_verdict_and_touches_nothing(tmp_path, monkeypatch, fake_registry) -> None:
    project = git_project(tmp_path, monkeypatch)
    (project / "feature.py").write_text("x = 1\n",
        encoding="utf-8")  # an uncommitted change to review
    before = _commits(project)

    result = runner.invoke(
        app, ["review", "-m", "[[output@reviewer:**Verdict** — APPROVE]]"], env={"COLUMNS": "220"}
    )
    assert result.exit_code == 0
    assert "APPROVE" in result.output
    # read-only: no commit, the change is still uncommitted, nothing new staged
    assert _commits(project) == before
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=project, capture_output=True, text=True
    ).stdout
    assert "feature.py" in status  # still there, untracked/unstaged — review changed nothing


def test_review_clean_tree_says_nothing_to_review(tmp_path, monkeypatch, fake_registry) -> None:
    git_project(tmp_path, monkeypatch)  # clean after the init commit
    result = runner.invoke(app, ["review"], env={"COLUMNS": "220"})
    assert result.exit_code == 0
    assert "nothing to review" in result.output


def test_review_not_a_git_repo_exit_2(tmp_path, monkeypatch, fake_registry) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    monkeypatch.chdir(plain)
    result = runner.invoke(app, ["review"])
    assert result.exit_code == 2
    assert "not a git repository" in result.output
