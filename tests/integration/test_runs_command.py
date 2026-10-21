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
        f"  fake: {{command: {FAKE_CLI}, timeout_s: 30}}\n", encoding="utf-8")
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


def test_runs_export_markdown_and_json(tmp_path, fake_registry, monkeypatch) -> None:
    """ADR-036: one row per run with cost, diff size and reviewer findings."""
    project = two_stage_project(tmp_path, monkeypatch)
    config = project / ".ai" / "config.yaml"
    config.write_text(config.read_text(encoding="utf-8").replace(
        "stages: [planner, coder]", "stages: [planner, coder, reviewer]"
    ).replace(
        "  coder: {provider: fake}\n", "  coder: {provider: fake}\n  reviewer: {provider: fake}\n"
    ), encoding="utf-8")
    import subprocess
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    subprocess.run(["git", "add", "-A"], cwd=project, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "i"],
                   cwd=project, check=True)
    req = ("build [[write@coder:app.py:x=1]] "
           "[[output@reviewer:**Verdict** — APPROVE WITH NOTES\n\nFindings\n1. minor — naming]]")
    assert runner.invoke(app, ["run", req]).exit_code == 0

    md = runner.invoke(app, ["runs", "export"], env={"COLUMNS": "300"})
    assert md.exit_code == 0, md.output
    header, sep, row = [ln for ln in md.output.splitlines() if ln.startswith("|")][:3]
    assert "findings (blocker / major / minor)" in header
    assert "| APPROVE WITH NOTES | 0 / 0 / 1 | 1 | +1/-0 |" in row

    js = runner.invoke(app, ["runs", "export", "--format", "json"])
    assert js.exit_code == 0, js.output
    import json
    data = json.loads(js.output)
    assert data[0]["files_changed"] == 1 and data[0]["findings"]["minor"] == 1
    assert data[0]["verdict"] == "APPROVE WITH NOTES"
    assert data[0]["stages"] == ["planner", "coder", "reviewer"]


def test_runs_export_unknown_id_is_a_usage_error(tmp_path, fake_registry, monkeypatch) -> None:
    two_stage_project(tmp_path, monkeypatch)
    result = runner.invoke(app, ["runs", "export", "nope"])
    assert result.exit_code == 2
