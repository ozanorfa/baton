"""Root Typer application. Thin by design: parse, delegate, render.

Bare `ai "<request>"` is sugar for `ai run "<request>"`: main() inserts the
`run` command when the first argument is not a known command or option.
"""

import sys

import typer

from ai_orchestrator import __version__
from ai_orchestrator.cli.commands.ask import ask
from ai_orchestrator.cli.commands.config_cmd import config_app
from ai_orchestrator.cli.commands.doctor import doctor
from ai_orchestrator.cli.commands.run import run

app = typer.Typer(
    name="ai",
    help="Local-first AI coding orchestrator: a deterministic pipeline over AI coding CLIs.",
    no_args_is_help=True,
    add_completion=False,
)
app.add_typer(config_app, name="config")
app.command()(doctor)
app.command()(ask)
app.command()(run)

_COMMANDS = {"run", "ask", "doctor", "config", "init", "runs", "resume"}


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"ai-orchestrator {__version__}")
        raise typer.Exit()


@app.callback()
def root(
    version: bool = typer.Option(
        False, "--version", callback=_version_callback, is_eager=True, help="Show version and exit."
    ),
) -> None:
    pass


def rewrite_argv(argv: list[str]) -> list[str]:
    """`ai "add feature"` → `ai run "add feature"` (also handles leading flags
    like --with-designer). Known commands and bare option-only calls pass through."""
    args = argv[1:]
    first_positional = next((a for a in args if not a.startswith("-")), None)
    if first_positional is None or first_positional in _COMMANDS:
        return argv
    return [argv[0], "run", *args]


def main() -> None:
    sys.argv = rewrite_argv(sys.argv)
    app()
