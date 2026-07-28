"""Root Typer application. Thin by design: parse, delegate, render.

Bare `batonai "<request>"` is sugar for `batonai run "<request>"`: main()
inserts the `run` command when the first argument is not a known command or
option. Bare `batonai` with no arguments at all opens the interactive wizard
(ADR-026) — unless stdin/stdout is not a terminal, where it prints help as
before so scripts and CI are unaffected.
"""

import sys

import typer

from ai_orchestrator import __version__
from ai_orchestrator.cli import wizard
from ai_orchestrator.cli.commands.ask import ask
from ai_orchestrator.cli.commands.config_cmd import config_app
from ai_orchestrator.cli.commands.doctor import doctor
from ai_orchestrator.cli.commands.health import health
from ai_orchestrator.cli.commands.init import init
from ai_orchestrator.cli.commands.publish import publish
from ai_orchestrator.cli.commands.resume import resume
from ai_orchestrator.cli.commands.review import review
from ai_orchestrator.cli.commands.revise import revise
from ai_orchestrator.cli.commands.run import run
from ai_orchestrator.cli.commands.runs import runs_app

app = typer.Typer(
    name="batonai",
    help="Local-first AI coding orchestrator: a deterministic pipeline over AI coding CLIs.",
    no_args_is_help=False,  # bare invocation opens the wizard instead (ADR-026)
    invoke_without_command=True,
    add_completion=False,
)
app.add_typer(config_app, name="config")
app.command()(doctor)
app.command()(health)
app.command()(ask)
app.command()(run)
app.command()(init)
app.add_typer(runs_app, name="runs")
app.command()(resume)
app.command()(revise)
app.command()(review)
app.command()(publish)

_COMMANDS = {
    "run", "ask", "doctor", "config", "init", "runs", "resume", "revise", "review",
    "publish", "health",
}


def _version_callback(value: bool) -> None:
    if value:
        # Names the installed package too: `batonai` is the command, but
        # `ai-orchestrator` is what `uv tool list` / `pip show` know it as.
        typer.echo(f"batonai (ai-orchestrator) {__version__}")
        raise typer.Exit()


@app.callback()
def root(
    ctx: typer.Context,
    version: bool = typer.Option(
        False, "--version", callback=_version_callback, is_eager=True, help="Show version and exit."
    ),
) -> None:
    if ctx.invoked_subcommand is not None:
        return
    if not wizard.is_interactive():
        # Piped or CI: the old no-args behaviour, so nothing hangs on input.
        typer.echo(ctx.get_help())
        raise typer.Exit()
    wizard.launch()


def rewrite_argv(argv: list[str]) -> list[str]:
    """`batonai "add feature"` → `batonai run "add feature"` (also handles leading flags
    like --with-designer). Known commands and bare option-only calls pass through."""
    args = argv[1:]
    first_positional = next((a for a in args if not a.startswith("-")), None)
    if first_positional is None or first_positional in _COMMANDS:
        return argv
    return [argv[0], "run", *args]


def main() -> None:
    sys.argv = rewrite_argv(sys.argv)
    app()
