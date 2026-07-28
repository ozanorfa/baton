"""T31: `batonai runs list` / `batonai runs show` against real run directories."""

from pathlib import Path

from typer.testing import CliRunner

from ai_orchestrator.cli.app import app

FAKE_CLI = Path(__file__).parent / "fake_provider" / "fake_ai.py"
runner = CliRunner()


def two_stage_project(tmp_path: Path, monkeypatch) -> Path:
    project = tmp_path / "proj"
    (project / ".ai").mkdir(parents=True)
    (project / ".ai" / "config.yaml").write_text(
        "pipeline:\n  stages: [planner, coder]\n"
        "roles:\n  planner: {provider: fake}\n  coder: {provider: fake}\n"
        "providers:\n"
        f"  fake: {{command: {FAKE_CLI}, timeout_s: 30}}\n"
    )
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.chdir(project)
    return project


def test_runs_list_and_show(tmp_path, fake_registry, monkeypatch) -> None:
    two_stage_project(tmp_path, monkeypatch)
    assert runner.invoke(app, ["run", "first request works"]).exit_code == 0
    assert runner.invoke(app, ["run", "second [[fail@coder:died]]"]).exit_code == 1

    listed = runner.invoke(app, ["runs", "list"], env={"COLUMNS": "220"})
    assert listed.exit_code == 0
    assert "succeeded" in listed.output and "failed" in listed.output
    assert "first request works" in listed.output
    assert "✓✓" in listed.output and "✓✗" in listed.output  # per-stage glyphs

    run_id = listed.output.split("2026-", 1)[1].split()[0]
    shown = runner.invoke(app, ["runs", "show", f"2026-{run_id}"], env={"COLUMNS": "220"})
    assert shown.exit_code == 0
    assert "request:" in shown.output
    assert "planner" in shown.output and "coder" in shown.output


def test_runs_list_empty_project(tmp_path, monkeypatch) -> None:
    (tmp_path / "empty").mkdir()
    monkeypatch.chdir(tmp_path / "empty")
    result = runner.invoke(app, ["runs", "list"])
    assert result.exit_code == 0
    assert "no runs yet" in result.output


def test_runs_show_unknown_id_exit_2(tmp_path, monkeypatch) -> None:
    (tmp_path / "empty").mkdir()
    monkeypatch.chdir(tmp_path / "empty")
    result = runner.invoke(app, ["runs", "show", "nope"])
    assert result.exit_code == 2
