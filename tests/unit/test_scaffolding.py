from typer.testing import CliRunner

from ai_orchestrator import __version__
from ai_orchestrator.cli.app import app

runner = CliRunner()


def test_version_flag() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output
