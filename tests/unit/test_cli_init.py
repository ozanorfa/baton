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
    # ADR-027: the ignore rule lives inside the directory baton owns, and the
    # project's root .gitignore is never touched.
    assert "runs/" in (tmp_path / ".ai" / ".gitignore").read_text()
    assert not (tmp_path / ".gitignore").exists()

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
    assert (tmp_path / ".ai" / ".gitignore").read_text().count("runs/") == 1  # no duplicate entry


def test_init_leaves_the_users_root_gitignore_untouched(tmp_path: Path, monkeypatch) -> None:
    """ADR-027: baton edits only files it owns."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".gitignore").write_text("node_modules/\n")
    runner.invoke(app, ["init"])
    assert (tmp_path / ".gitignore").read_text() == "node_modules/\n", "unmodified, byte for byte"
    assert "runs/" in (tmp_path / ".ai" / ".gitignore").read_text()


def test_init_respects_a_legacy_root_gitignore_entry(tmp_path: Path, monkeypatch) -> None:
    """A project set up by an older baton keeps working — no duplicate rule."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".gitignore").write_text("# AI orchestrator run history (local)\n.ai/runs/\n")
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    assert not (tmp_path / ".ai" / ".gitignore").exists(), "the existing rule already covers it"
    assert (tmp_path / ".gitignore").read_text().count(".ai/runs/") == 1


def test_starter_config_yaml_is_valid_yaml(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["init"])
    data = yaml.safe_load((tmp_path / ".ai" / "config.yaml").read_text())
    assert data["roles"]["designer"]["enabled"] is False


def test_init_detects_stack_from_marker_files(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    (tmp_path / "pubspec.yaml").write_text("name: app\n")
    runner.invoke(app, ["init"])
    profile = (tmp_path / ".ai" / "project.md").read_text()
    assert "Detected: Flutter/Dart (pubspec.yaml); Python (pyproject.toml)" in profile
    assert "e.g.:" not in profile.split("## Structure")[0]  # no framework name-dropping


def test_init_without_markers_stays_neutral(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["init"])
    profile = (tmp_path / ".ai" / "project.md").read_text()
    assert "Nothing was auto-detected" in profile
    assert "Flutter" not in profile  # no misleading framework examples anywhere
    assert "Riverpod" not in profile
