"""T25: the optional Designer stage — off by default, enabled via config or
--with-designer, exercised through the real CLI on the fake provider."""

from pathlib import Path

from typer.testing import CliRunner

from ai_orchestrator.cli.app import app

FAKE_CLI = Path(__file__).parent / "fake_provider" / "fake_ai.py"
runner = CliRunner()


def four_role_project(tmp_path: Path, monkeypatch) -> Path:
    project = tmp_path / "proj"
    (project / ".ai").mkdir(parents=True)
    (project / ".ai" / "config.yaml").write_text(
        "roles:\n"
        "  planner: {provider: fake}\n"
        "  designer: {provider: fake}\n"  # enabled: not set → default False
        "  coder: {provider: fake}\n"
        "  reviewer: {provider: fake}\n"
        "providers:\n"
        f"  fake: {{command: {FAKE_CLI}, timeout_s: 30}}\n", encoding="utf-8")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.chdir(project)
    return project


def test_designer_skipped_by_default(tmp_path, fake_registry, monkeypatch) -> None:
    project = four_role_project(tmp_path, monkeypatch)
    result = runner.invoke(app, ["run", "add feature"], env={"COLUMNS": "200"})
    assert result.exit_code == 0
    assert "designer skipped" in result.output
    run_dir = next((project / ".ai" / "runs").iterdir())
    assert not (run_dir / "artifacts" / "design.md").exists()
    assert (run_dir / "artifacts" / "review.md").exists()  # rest of pipeline ran


def test_with_designer_flag_enables_stage(tmp_path, fake_registry, monkeypatch) -> None:
    project = four_role_project(tmp_path, monkeypatch)
    result = runner.invoke(app, ["run", "--with-designer", "add feature"], env={"COLUMNS": "200"})
    assert result.exit_code == 0
    assert "designer skipped" not in result.output
    assert "✓ designer" in result.output
    run_dir = next((project / ".ai" / "runs").iterdir())
    assert (run_dir / "artifacts" / "design.md").exists()
    # contract flow: coder prompt embeds the design artifact
    coder_prompt = (run_dir / "prompts" / "03-coder.md").read_text(encoding="utf-8")
    assert (run_dir / "artifacts" / "design.md").read_text(encoding="utf-8").strip() in coder_prompt


def test_config_enabled_designer_runs_without_flag(tmp_path, fake_registry, monkeypatch) -> None:
    project = four_role_project(tmp_path, monkeypatch)
    config = project / ".ai" / "config.yaml"
    config.write_text(config.read_text(encoding="utf-8").replace(
        "designer: {provider: fake}", "designer: {provider: fake, enabled: true}"
    ))
    result = runner.invoke(app, ["run", "add feature"], env={"COLUMNS": "200"})
    assert result.exit_code == 0
    assert "✓ designer" in result.output
