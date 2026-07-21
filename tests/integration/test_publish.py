"""ADR-020: `ai publish` — the single, user-triggered git-writing command.

Preview mode never touches git; --commit commits; --push commits + pushes; a
rejected confirmation does nothing. No pipeline role runs git (ADR-014 intact).
"""

import subprocess
from pathlib import Path

from typer.testing import CliRunner

from ai_orchestrator.cli.app import app

runner = CliRunner()


def git_repo(tmp_path: Path, monkeypatch, *, with_remote: bool = False) -> Path:
    project = tmp_path / "proj"
    project.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=project, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=project, check=True)
    (project / "seed.txt").write_text("seed")
    subprocess.run(["git", "add", "-A"], cwd=project, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=project, check=True)
    if with_remote:
        remote = tmp_path / "remote.git"
        subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
        subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=project, check=True)
        subprocess.run(["git", "push", "-q", "-u", "origin", "HEAD"], cwd=project, check=True)
    monkeypatch.chdir(project)
    return project


def _commits(project: Path) -> int:
    out = subprocess.run(
        ["git", "rev-list", "--count", "HEAD"], cwd=project, capture_output=True, text=True
    ).stdout.strip()
    return int(out)


def test_preview_only_never_touches_git(tmp_path, monkeypatch) -> None:
    project = git_repo(tmp_path, monkeypatch)
    (project / "change.txt").write_text("new")
    before = _commits(project)
    result = runner.invoke(app, ["publish", "-m", "feat: a change"])
    assert result.exit_code == 0
    assert "commit message" in result.output
    assert _commits(project) == before  # nothing committed


def test_commit_creates_a_commit_and_cleans_tree(tmp_path, monkeypatch) -> None:
    project = git_repo(tmp_path, monkeypatch)
    (project / "change.txt").write_text("new")
    before = _commits(project)
    result = runner.invoke(app, ["publish", "-m", "feat: a change", "--commit", "--yes"])
    assert result.exit_code == 0
    assert "✓ committed" in result.output
    assert _commits(project) == before + 1
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=project, capture_output=True, text=True
    )
    assert status.stdout.strip() == ""  # git add -A staged everything
    subject = subprocess.run(
        ["git", "log", "-1", "--pretty=%s"], cwd=project, capture_output=True, text=True
    ).stdout
    assert "feat: a change" in subject


def test_rejected_confirmation_commits_nothing(tmp_path, monkeypatch) -> None:
    project = git_repo(tmp_path, monkeypatch)
    (project / "change.txt").write_text("new")
    before = _commits(project)
    result = runner.invoke(app, ["publish", "-m", "x", "--commit"], input="n\n")
    assert result.exit_code == 0
    assert "aborted" in result.output
    assert _commits(project) == before


def test_push_updates_the_remote(tmp_path, monkeypatch) -> None:
    project = git_repo(tmp_path, monkeypatch, with_remote=True)
    (project / "change.txt").write_text("new")
    before = _commits(project)
    result = runner.invoke(app, ["publish", "-m", "feat: pushed", "--push", "--yes"])
    assert result.exit_code == 0
    assert "✓ committed" in result.output and "✓ pushed" in result.output
    assert _commits(project) == before + 1
    remote_log = subprocess.run(
        ["git", "--git-dir", str(tmp_path / "remote.git"), "log", "--oneline", "--all"],
        capture_output=True, text=True,
    ).stdout
    assert "feat: pushed" in remote_log


def test_not_a_git_repo_errors(tmp_path, monkeypatch) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    monkeypatch.chdir(plain)
    result = runner.invoke(app, ["publish", "-m", "x", "--commit", "--yes"])
    assert result.exit_code == 2
    assert "not a git repository" in result.output
