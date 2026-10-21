"""Root Typer application. Thin by design: parse, delegate, render.

Bare `batonai "<request>"` is sugar for `batonai run "<request>"`: main()
inserts the `run` command when the first argument is not a known command or
option. Bare `batonai` with no arguments at all opens the interactive wizard
(ADR-026) — unless stdin/stdout is not a terminal, where it prints help as
before so scripts and CI are unaffected.
"""

import sys
import warnings

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
from ai_orchestrator.cli.commands.setup import setup

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
app.command()(setup)
app.command()(ask)
app.command()(run)
app.command()(init)
app.add_typer(runs_app, name="runs")
app.command()(resume)
app.command()(revise)
app.command()(review)
app.command()(publish)



def _known_commands() -> set[str]:
    """Every registered command and sub-app name, read from Typer itself.

    Derived, not hand-maintained (ADR-034): a hand-written set silently fell
    out of step whenever a command was added, and then `batonai <newcmd>` was
    rewritten into `batonai run "<newcmd>"` — a pipeline run by accident.
    """
    names = {
        info.name or (info.callback.__name__ if info.callback else "")
        for info in app.registered_commands
    }
    names |= {group.name for group in app.registered_groups if group.name}
    names.discard("")
    return names


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"batonai {__version__}")
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
    if first_positional is None or first_positional in _known_commands():
        return argv
    return [argv[0], "run", *args]


def _show_warning(message, category, filename, lineno, file=None, line=None) -> None:
    """Config warnings (unknown keys, broken plugins) as one tidy CLI line.

    Python's default `warnings` formatter prints `path/to/loader.py:274:
    UserWarning: …` — an internal file path and a Python class name that mean
    nothing to someone editing `.ai/config.yaml` (ADR-034).
    """
    from ai_orchestrator.cli import render

    render.console.print(f"[yellow]⚠ {message}[/yellow]")


def main() -> None:
    warnings.showwarning = _show_warning
    sys.argv = rewrite_argv(sys.argv)
    app()
