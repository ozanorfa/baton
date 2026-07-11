from pathlib import Path

import yaml
from typer.testing import CliRunner

from ai_orchestrator.cli.app import app
from ai_orchestrator.config.loader import load_config
from ai_orchestrator.config.schema import AppConfig

runner = CliRunner()


def test_init_creates_documented_footprint(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0

    assert (tmp_path / ".ai" / "config.yaml").is_file()
    assert (tmp_path / ".ai" / "project.md").is_file()
    assert (tmp_path / ".ai" / "prompts").is_dir()
    assert ".ai/runs/" in (tmp_path / ".gitignore").read_text()

    # the starter config must be loadable and valid against the schema
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    loaded = load_config(tmp_path, env={})
    assert isinstance(loaded.config, AppConfig)
    assert loaded.config.roles["coder"].provider == "claude"


def test_init_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["init"])
    (tmp_path / ".ai" / "project.md").write_text("MY CUSTOM PROFILE")

    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    assert "nothing to do" in result.output
    assert (tmp_path / ".ai" / "project.md").read_text() == "MY CUSTOM PROFILE"  # never clobbered
    assert (tmp_path / ".gitignore").read_text().count(".ai/runs/") == 1  # no duplicate entry


def test_init_appends_to_existing_gitignore(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".gitignore").write_text("node_modules/\n")
    runner.invoke(app, ["init"])
    content = (tmp_path / ".gitignore").read_text()
    assert content.startswith("node_modules/")
    assert ".ai/runs/" in content


def test_starter_config_yaml_is_valid_yaml(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["init"])
    data = yaml.safe_load((tmp_path / ".ai" / "config.yaml").read_text())
    assert data["roles"]["designer"]["enabled"] is False
