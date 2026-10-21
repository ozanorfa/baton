import sys
from pathlib import Path

from typer.testing import CliRunner

from ai_orchestrator.cli.app import app

runner = CliRunner()
# Exits 0 for `<OK_BIN> --version` on every platform (prints the interpreter version).
OK_BIN = sys.executable

# A stand-in "claude" CLI: reads stdin, emits valid claude-shaped JSON.
FAKE_CLAUDE = (
    "import sys, json; p = sys.stdin.read(); "
    "print(json.dumps({'type': 'result', 'subtype': 'success', 'is_error': False, "
    "'result': 'echo:' + p, 'session_id': 's-1', 'total_cost_usd': 0.01, "
    "'usage': {'input_tokens': 5, 'output_tokens': 7}}))"
)


def setup_project(tmp_path: Path, monkeypatch, command: str) -> None:
    project = tmp_path / "proj"
    (project / ".ai").mkdir(parents=True)
    (project / ".ai" / "config.yaml").write_text(
        f"providers:\n  claude:\n    command: {command}\n"
        "roles:\n  coder: {provider: claude}\n"
    )
    monkeypatch.chdir(project)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))


def make_fake_cli(tmp_path: Path) -> Path:
    """A single-token executable wrapping the fake: a .sh on POSIX, a .cmd on
    Windows — the same shape the real npm-installed CLIs have there."""
    body = tmp_path / "fake_claude.py"
    body.write_text(FAKE_CLAUDE + "\n", encoding="utf-8")
    if sys.platform == "win32":
        script = tmp_path / "fake_claude.cmd"
        script.write_text(f'@"{sys.executable}" "{body}" %*\r\n', encoding="utf-8")
    else:
        script = tmp_path / "fake_claude.sh"
        script.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{body}" "$@"\n', encoding="utf-8")
        script.chmod(0o755)
    return script


def test_ask_round_trips_through_role_provider(tmp_path: Path, monkeypatch) -> None:
    setup_project(tmp_path, monkeypatch, str(make_fake_cli(tmp_path)))
    result = runner.invoke(app, ["ask", "--role", "coder", "hello there"])
    assert result.exit_code == 0
    assert "echo:hello there" in result.output
    assert "coder → claude" in result.output
    assert "5/7" in result.output  # usage line rendered
    assert "s-1" in result.output


def test_ask_unknown_role_exits_2(tmp_path: Path, monkeypatch) -> None:
    setup_project(tmp_path, monkeypatch, OK_BIN)
    result = runner.invoke(app, ["ask", "--role", "wizard", "hi"])
    assert result.exit_code == 2
    assert "unknown role 'wizard'" in result.output


def test_ask_provider_failure_exits_1(tmp_path: Path, monkeypatch) -> None:
    setup_project(tmp_path, monkeypatch, "/nonexistent/claude-bin")
    result = runner.invoke(app, ["ask", "--role", "coder", "hi"])
    assert result.exit_code == 1
    assert "binary not found" in result.output
