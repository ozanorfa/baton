"""`ai config` subcommands."""

import typer

from ai_orchestrator.cli import render
from ai_orchestrator.config.loader import ConfigError, load_config

config_app = typer.Typer(help="Inspect configuration.", no_args_is_help=True)


@config_app.command("show")
def show() -> None:
    """Print the merged effective configuration and where each value came from."""
    try:
        loaded = load_config()
    except ConfigError as exc:
        render.render_error(str(exc))
        raise typer.Exit(code=2) from exc
    render.render_config(loaded)
