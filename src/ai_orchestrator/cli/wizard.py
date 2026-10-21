"""The interactive front door: bare `batonai` with no arguments (ADR-026).

A one-shot guided wizard — scan, report, offer the missing setup, take the
request, hand off to the *same* `run` code path, exit. It holds no pipeline
logic of its own: everything it can do, a flag can already do, which is what
keeps the two entry paths from drifting.

Not a REPL. A persistent session is a deliberate later step (ADR-026), and it
would wrap `scan`/`decide` rather than replace them.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import typer

from ai_orchestrator.cli import render, scan
from ai_orchestrator.cli.commands.init import init
from ai_orchestrator.cli.commands.publish import publish
from ai_orchestrator.cli.commands.review import review
from ai_orchestrator.cli.commands.revise import revise
from ai_orchestrator.cli.commands.run import run
from ai_orchestrator.cli.scan import Step
from ai_orchestrator.config.loader import ConfigError, load_config
from ai_orchestrator.transport.headless import HeadlessTransport

GIT_INIT_TIMEOUT_S = 15


def is_interactive() -> bool:
    """The wizard requires a real terminal on both ends.

    Piped/CI invocations must behave exactly as before (ADR-026): a wizard that
    blocks on `input()` in a pipeline would be a hang, not a feature.
    """
    return sys.stdin.isatty() and sys.stdout.isatty()


def _git_init(project_dir: Path) -> bool:
    try:
        proc = subprocess.run(
            ["git", "init", "-q"],
            cwd=project_dir, capture_output=True, text=True,
            timeout=GIT_INIT_TIMEOUT_S, shell=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        render.console.print(f"[yellow]  could not run git init: {exc}[/yellow]")
        return False
    if proc.returncode != 0:
        render.console.print(f"[yellow]  git init failed: {proc.stderr.strip()}[/yellow]")
        return False
    render.console.print("  [green]created[/green] .git/")
    # ADR-029: a fresh repo has no baseline; say so now rather than let the user
    # discover it as a confusing dirty-tree warning seconds later.
    render.console.print(
        "  [dim]tip: commit your existing files before running, so the coder's "
        'diff is only its own work — git add -A && git commit -m "initial commit"[/dim]'
    )
    return True


def _ask_nonempty(question: str) -> str:
    """Prompt until a non-empty answer is given; Ctrl-C/EOF exits cleanly."""
    while True:
        answer = typer.prompt(f"\n  {question}\n  ", prompt_suffix="").strip()
        if answer:
            return answer
        render.console.print("[dim]  (enter a request, or press Ctrl-C to quit)[/dim]")


def _ask_request() -> str:
    return _ask_nonempty("What do you want done?")


MENU = (
    ("New request", "run"),
    ("Revise the last run", "revise"),
    ("Review my current changes", "review"),
    ("Preview a commit message for pending changes", "publish"),
    ("Quit", "quit"),
)


def _ask_menu(state: scan.WorkspaceScan) -> str:
    render.console.print("  [bold]What next?[/bold]")
    for number, (label, _) in enumerate(MENU, start=1):
        render.console.print(f"   [bold]{number}[/bold]  {label}")
    choice = typer.prompt("\n  choose", default="1", show_default=True).strip()
    try:
        index = int(choice)
    except ValueError:
        return "run"
    if 1 <= index <= len(MENU):
        return MENU[index - 1][1]
    return "run"


def _dispatch(action: str, state: scan.WorkspaceScan, health: bool) -> None:
    """Hand off to the existing commands.

    Every argument is passed explicitly: these are Typer command functions, so
    their declared defaults are `OptionInfo` objects, not values — calling them
    positionally would smuggle those objects in as if they were user input.
    """
    if action == "quit":
        return
    if action == "run":
        run(
            request=_ask_request(),
            with_designer=False, with_tester=False, with_publisher=False,
            fix_loop=False, health=health,
        )
    elif action == "revise":
        revise(
            correction=_ask_nonempty("What should change?"), run_id=None, from_stage=None,
            with_designer=False, with_tester=False, with_publisher=False,
        )
    elif action == "review":
        review(message=None)
    elif action == "publish":
        publish(message=None, commit=False, push=False, yes=False)
        render.console.print(
            "[dim]  preview only — run `batonai publish --commit` (or --push) to commit.[/dim]"
        )


def launch() -> None:
    """Entry point for bare `batonai`. Raises typer.Exit with the usual codes.

    Ctrl-C or EOF at any *prompt* is a clean cancellation (ADR-026): exit 130,
    the conventional SIGINT code, with nothing created — Typer's own default
    would be a bare "Aborted." and exit 1, which is indistinguishable from a
    stage failure. A Ctrl-C *during a pipeline stage* never reaches here: the
    `run` command renders the interrupted run's summary itself and exits 130
    (ADR-034) — so this message is only ever true when it is shown.
    """
    try:
        _launch()
    except (KeyboardInterrupt, EOFError, typer.Abort) as exc:
        render.console.print("\n[dim]cancelled — nothing was changed.[/dim]")
        raise typer.Exit(code=130) from exc


def _launch() -> None:
    project_dir = Path.cwd()

    try:
        loaded = load_config(project_dir)
    except ConfigError as exc:
        render.render_error(str(exc))
        raise typer.Exit(code=2) from exc

    render.render_banner()
    with render.console.status(f"[dim]scanning {project_dir.name}/ …[/dim]"):
        state = scan.scan(project_dir, loaded.config, HeadlessTransport())
    render.render_scan(state)

    steps = scan.decide(state)

    if Step.BLOCK in steps:
        render.render_error(
            "a provider needed by this project's pipeline is unavailable — "
            "fix it (see `batonai doctor`) and try again."
        )
        raise typer.Exit(code=2)

    # An explicit request has to be collected before setup in the greenfield
    # row, so it is held here and reused by the RUN step below.
    request: str | None = None
    for step in steps:
        if step is Step.ASK_REQUEST:
            request = _ask_request()
        elif step is Step.GIT_INIT:
            if typer.confirm("  Initialize a git repository here?", default=True):
                _git_init(project_dir)
        elif step is Step.BATON_INIT:
            if typer.confirm("  Set up baton in this folder?", default=True):
                init(models=True)  # explicit: Typer defaults are OptionInfo objects
                render.console.print()
        elif step is Step.RUN:
            assert request is not None  # ASK_REQUEST always precedes RUN
            run(
                request=request,
                with_designer=False, with_tester=False, with_publisher=False,
                fix_loop=False, health=bool(state.health),
            )
        elif step is Step.MENU:
            _dispatch(_ask_menu(state), state, health=bool(state.health))
