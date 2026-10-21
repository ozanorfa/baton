import sys
from pathlib import Path

from typer.testing import CliRunner

from ai_orchestrator.cli.app import app

runner = CliRunner()
# Exits 0 for `<OK_BIN> --version` on every platform (prints the interpreter version).
OK_BIN = sys.executable


def setup_project(tmp_path: Path, monkeypatch, config_text: str) -> None:
    project = tmp_path / "proj"
    (project / ".ai").mkdir(parents=True)
    (project / ".ai" / "config.yaml").write_text(config_text)
    monkeypatch.chdir(project)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))


def test_doctor_healthy_with_fake_commands(tmp_path: Path, monkeypatch) -> None:
    # {OK_BIN} exits 0 for any argv → every health check passes. doctor
    # checks EVERY configured provider, so all of them must resolve to a working
    # binary — not just the three used by the default enabled roles (else this
    # fails on a machine without opencode installed, e.g. CI).
    setup_project(
        tmp_path,
        monkeypatch,
        "providers:\n"
        f"  claude: {{command: {OK_BIN}}}\n"
        f"  codex: {{command: {OK_BIN}}}\n"
        f"  antigravity: {{command: {OK_BIN}}}\n"
        f"  opencode: {{command: {OK_BIN}}}\n"
        f"  deterministic: {{command: {OK_BIN}}}\n"
        f"  testrunner: {{command: {OK_BIN}}}\n",
    )
    result = runner.invoke(app, ["doctor"], env={"COLUMNS": "200"})
    assert result.exit_code == 0
    assert "healthy" in result.output
    assert "planner, reviewer" in result.output  # role bindings shown per provider


def test_doctor_missing_binary_is_actionable_row_not_crash(tmp_path: Path, monkeypatch) -> None:
    setup_project(
        tmp_path,
        monkeypatch,
        "providers:\n"
        f"  claude: {{command: {OK_BIN}}}\n"
        "  codex: {command: /nonexistent/codex-bin}\n"
        f"  antigravity: {{command: {OK_BIN}}}\n",
    )
    result = runner.invoke(app, ["doctor"], env={"COLUMNS": "200"})
    assert result.exit_code == 1  # unhealthy → nonzero for scripts
    assert "binary not found" in result.output
    assert "healthy" in result.output  # others still reported


def test_doctor_unregistered_provider_named(tmp_path: Path, monkeypatch) -> None:
    setup_project(
        tmp_path,
        monkeypatch,
        "roles:\n  planner: {provider: mystery}\n"
        "providers:\n  mystery: {command: whatever}\n",
    )
    result = runner.invoke(app, ["doctor"], env={"COLUMNS": "250"})
    assert result.exit_code == 1
    assert "unknown provider" in result.output


def test_doctor_missing_optional_provider_does_not_fail(tmp_path: Path, monkeypatch) -> None:
    """opencode/antigravity serve stages that are OFF by default; a machine without
    them can run the whole default pipeline, so doctor must not report failure."""
    setup_project(
        tmp_path,
        monkeypatch,
        "providers:\n"
        f"  claude: {{command: {OK_BIN}}}\n"
        f"  codex: {{command: {OK_BIN}}}\n"
        "  antigravity: {command: /nonexistent/agy}\n"
        "  opencode: {command: /nonexistent/opencode}\n",
    )
    result = runner.invoke(app, ["doctor"], env={"COLUMNS": "200"})
    assert result.exit_code == 0, result.output
    assert "optional" in result.output
    assert "designer (off)" in result.output and "publisher (off)" in result.output


def test_doctor_missing_optional_provider_fails_once_its_stage_is_enabled(
    tmp_path: Path, monkeypatch
) -> None:
    setup_project(
        tmp_path,
        monkeypatch,
        "roles:\n  publisher: {enabled: true}\n"
        "providers:\n"
        f"  claude: {{command: {OK_BIN}}}\n"
        f"  codex: {{command: {OK_BIN}}}\n"
        "  opencode: {command: /nonexistent/opencode}\n",
    )
    result = runner.invoke(app, ["doctor"], env={"COLUMNS": "200"})
    assert result.exit_code == 1
    assert "✗" in result.output
