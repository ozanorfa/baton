from pathlib import Path

from typer.testing import CliRunner

from ai_orchestrator.cli.app import app

runner = CliRunner()


def test_config_show_renders_values_and_sources(tmp_path: Path, monkeypatch) -> None:
    project = tmp_path / "proj"
    (project / ".ai").mkdir(parents=True)
    (project / ".ai" / "config.yaml").write_text("providers:\n  claude:\n    timeout_s: 1234\n")
    monkeypatch.chdir(project)
    # isolate from the real user config
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    result = runner.invoke(app, ["config", "show"], env={"COLUMNS": "200"})

    assert result.exit_code == 0
    assert "providers.claude.timeout_s" in result.output
    assert "1234" in result.output
    assert "project" in result.output  # project value annotated with its source
    assert "defaults" in result.output  # untouched values annotated too


def test_config_show_invalid_config_exits_2(tmp_path: Path, monkeypatch) -> None:
    project = tmp_path / "proj"
    (project / ".ai").mkdir(parents=True)
    (project / ".ai" / "config.yaml").write_text("providers:\n  claude:\n    timeout_s: -1\n")
    monkeypatch.chdir(project)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    result = runner.invoke(app, ["config", "show"])

    assert result.exit_code == 2
