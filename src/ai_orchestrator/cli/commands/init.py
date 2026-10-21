"""`batonai init` — bootstrap .ai/ in a project (PROJECT_STRUCTURE.md §2.1).

Idempotent: existing files are never overwritten, only reported. `.ai/runs/`
is gitignored (local history); config.yaml and project.md are meant to be
committed and shared with the team.
"""

import sys
from pathlib import Path

import typer

from ai_orchestrator.cli import model_catalog, render
from ai_orchestrator.context.awareness import stack_labels  # single source of truth

# ADR-031: baton pins no model of its own, so whatever each CLI is configured to
# do silently decides cost and speed — on one machine that was codex/gpt-5.6-sol
# and claude/opus, neither chosen for the project, neither visible from baton.
# Setup offers the choice; "use the CLI's default" stays the default, so pressing
# Enter changes nothing for anyone. Suggestions/hints live in `model_catalog`,
# shared with `batonai setup` — they used to be duplicated per command, which is
# how `codex` ended up with neither (found live, 2026-07-29).


def prompt_models(providers: list[str]) -> dict[str, str]:
    """Ask which model each provider should use. {} means "leave every default".

    Only ever called with a terminal on both ends — `batonai init` in a script
    must not block on input.
    """
    chosen: dict[str, str] = {}
    render.console.print(
        "\n[bold]Model per provider[/bold] [dim](Enter = keep the CLI's own "
        "setting, which is what happens today)[/dim]"
    )
    for provider in providers:
        command = model_catalog.DEFAULT_COMMANDS.get(provider, provider)
        suggestions = model_catalog.suggestions_for(provider, command)
        if hint := model_catalog.hint_for(provider):
            render.console.print(f"  [dim]{hint}[/dim]")
        # Plain text: typer.prompt writes straight to the stream and does not
        # interpret Rich markup, so tags here would be printed literally.
        label = f"  {provider}"
        if suggestions:
            label += f" ({'/'.join(suggestions)})"
        answer = typer.prompt(label, default="", show_default=False).strip()
        if answer:
            chosen[provider] = answer
    return chosen


def render_model_block(models: dict[str, str]) -> str:
    """The `providers:` YAML appended to the starter config for chosen models."""
    if not models:
        return ""
    lines = [
        "",
        "# Model pinned per project (ADR-031). Remove a line to fall back to",
        "# whatever that CLI is configured to use on this machine.",
        "providers:",
    ]
    lines += [f"  {name}: {{model: {model}}}" for name, model in sorted(models.items())]
    return "\n".join(lines) + "\n"


def _interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()

STARTER_CONFIG = """\
# AI Orchestrator — project configuration (commit this file)
# Anything omitted falls back to user config (~/.config/batonai/config.yaml)
# and built-in defaults. `batonai config show` prints the merged result with sources.

# The built-in stage order; trim it per project, e.g. a plan+code-only pipeline:
# pipeline:
#   stages: [planner, coder]
# (default: [planner, designer, coder, tester, reviewer, publisher] — designer,
#  tester and publisher are optional and off unless enabled below or per run)

roles:
  planner: {provider: codex}
  designer: {provider: antigravity, enabled: false} # enable per-run with --with-designer
  coder: {provider: claude}
  tester: {provider: testrunner, enabled: false}    # zero-LLM; --with-tester
  reviewer: {provider: codex}
  publisher: {provider: opencode, enabled: false}   # drafts only; --with-publisher

# providers:
#   claude: {command: claude, model: null, timeout_s: 900}
#   # allow_commands: true lets the Coder run tests/linters to verify its work;
#   # git history and remote commands stay blocked regardless (ADR-034).
#   codex: {command: codex, timeout_s: 600}
#   antigravity: {command: agy, timeout_s: 600}
"""

STARTER_PROFILE = """\
# Project profile

Every AI role in the pipeline reads this file. Keep it short and factual —
it is sent with every stage, so every line here costs tokens on every run.

## Stack

{stack}

## Structure & conventions

<!-- Describe the layout and rules a new team member would need, e.g.:
     "feature-first layout under src/features/; tests mirror src/;
     snake_case files; English identifiers." -->

## Things AI assistants get wrong in this project

<!-- List project-specific corrections, e.g.: "we use library X for state,
     never suggest its common alternative." -->
"""

def detect_stack(project: Path) -> str:
    detected = stack_labels(project)
    if detected:
        return (
            "Detected: " + "; ".join(detected) + ".\n"
            "<!-- Auto-detected from marker files — refine with versions and key "
            "libraries, e.g. framework version, state management, backend. -->"
        )
    return (
        "<!-- Describe the stack, e.g.: language + version, framework, "
        "key libraries, backend services. Nothing was auto-detected. -->"
    )


GITIGNORE_ENTRY = ".ai/runs/"  # legacy root-.gitignore form; still honoured if present

# Baton's ignore rule lives inside the directory it owns (ADR-027). Git applies
# a .gitignore to its own directory and below, so `runs/` here is exactly
# `.ai/runs/` — and because .ai/ is excluded from diff capture, this file never
# shows up in a run's diff the way a root-.gitignore edit did.
NESTED_GITIGNORE = (
    "# AI orchestrator local state (run history + the code-health cache)\n"
    "runs/\nhealth.json\n"
)


def init(
    models: bool = typer.Option(
        True, "--models/--no-models",
        help="Ask which model each provider should use (ADR-031). Skipped without a terminal.",
    ),
) -> None:
    """Bootstrap .ai/ in the current directory (config, project profile, gitignore)."""
    project = Path.cwd()
    ai_dir = project / ".ai"
    created: list[str] = []
    skipped: list[str] = []

    (ai_dir / "prompts").mkdir(parents=True, exist_ok=True)

    config_content = STARTER_CONFIG
    if models and _interactive() and not (ai_dir / "config.yaml").exists():
        # Only when a config is actually being created: re-asking on an idempotent
        # re-run would imply an edit that never happens (existing files are kept).
        config_content += render_model_block(prompt_models(["claude", "codex"]))
        render.console.print(
            "\n[dim]tip: `batonai setup` changes which AI handles each role, and "
            "any model, at any time.[/dim]"
        )

    profile = STARTER_PROFILE.format(stack=detect_stack(project))
    for path, content in (
        (ai_dir / "config.yaml", config_content),
        (ai_dir / "project.md", profile),
    ):
        rel = str(path.relative_to(project))
        if path.exists():
            skipped.append(rel)
        else:
            path.write_text(content)
            created.append(rel)

    # ADR-027: never touch the project's root .gitignore — it is the user's
    # file, and editing it made baton's own bookkeeping show up as part of the
    # coder's diff on a first run (a live reviewer spent a finding on it).
    root_gitignore = project / ".gitignore"
    nested = ai_dir / ".gitignore"
    if root_gitignore.is_file() and GITIGNORE_ENTRY in root_gitignore.read_text():
        # Set up by an older baton: the rule is already in force, leave it be.
        skipped.append(f".gitignore ({GITIGNORE_ENTRY} already present)")
    elif nested.exists():
        skipped.append(".ai/.gitignore")
    else:
        nested.write_text(NESTED_GITIGNORE)
        created.append(".ai/.gitignore (ignores .ai/runs/)")

    for rel in created:
        render.console.print(f"  [green]created[/green] {rel}")
    for rel in skipped:
        render.console.print(f"  [dim]kept    {rel} (already exists)[/dim]")

    if created:
        render.console.print(
            "\n[bold]next:[/bold] fill in .ai/project.md — it is the single highest-leverage "
            "file for output quality and token efficiency."
        )
    else:
        render.console.print("nothing to do — project already initialized.")
