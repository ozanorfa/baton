"""Root Typer application. Thin by design: parse, delegate, render."""

import typer

from ai_orchestrator import __version__

app = typer.Typer(
    name="ai",
    help="Local-first AI coding orchestrator: a deterministic pipeline over AI coding CLIs.",
    no_args_is_help=True,
    add_completion=False,
)


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


def main() -> None:
    app()
