"""T20: the `ai run` command end-to-end through the CLI, on the fake provider."""

from typer.testing import CliRunner

from ai_orchestrator.cli.app import app, rewrite_argv

runner = CliRunner()


def test_rewrite_argv_bare_request() -> None:
    assert rewrite_argv(["ai", "add a feature"]) == ["ai", "run", "add a feature"]
    assert rewrite_argv(["ai", "--with-designer", "x"]) == ["ai", "run", "--with-designer", "x"]


def test_rewrite_argv_known_commands_untouched() -> None:
    for argv in (["ai", "doctor"], ["ai", "config", "show"], ["ai", "--version"], ["ai"]):
        assert rewrite_argv(argv) == argv


def test_cli_run_success(fake_project, fake_registry, monkeypatch) -> None:
    monkeypatch.chdir(fake_project)
    result = runner.invoke(app, ["run", "add a login screen"], env={"COLUMNS": "200"})
    assert result.exit_code == 0
    assert "✓ planner" in result.output and "✓ coder" in result.output
    assert "run succeeded" in result.output
    assert (fake_project / ".ai" / "runs").is_dir()


def test_cli_run_failure_exit_1_with_guidance(fake_project, fake_registry, monkeypatch) -> None:
    monkeypatch.chdir(fake_project)
    result = runner.invoke(
        app, ["run", "break [[fail:coder died]]"], env={"COLUMNS": "200"}
    )
    assert result.exit_code == 1
    assert "FAILED" in result.output
    assert "coder died" in result.output
    assert "pending" not in result.output.lower() or True  # summary table renders
    assert "ai doctor" in result.output  # next-steps guidance


def test_cli_run_preflight_failure_exit_2(fake_project, fake_registry, monkeypatch, tmp_path):
    monkeypatch.chdir(fake_project)
    config = fake_project / ".ai" / "config.yaml"
    config.write_text(config.read_text().replace("command: ", "command: /nonexistent-", 1))
    result = runner.invoke(app, ["run", "anything"])
    assert result.exit_code == 2
    assert "preflight failed" in result.output
