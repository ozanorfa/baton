"""`batonai init` — bootstrap .ai/ in a project (PROJECT_STRUCTURE.md §2.1).

Idempotent: existing files are never overwritten, only reported. `.ai/runs/`
is gitignored (local history); config.yaml and project.md are meant to be
committed and shared with the team.
"""

from pathlib import Path

from ai_orchestrator.cli import render
from ai_orchestrator.context.awareness import stack_labels  # single source of truth

STARTER_CONFIG = """\
# AI Orchestrator — project configuration (commit this file)
# Anything omitted falls back to user config (~/.config/ai-orchestrator/config.yaml)
# and built-in defaults. `batonai config show` prints the merged result with sources.

# pipeline:
#   stages: [planner, designer, coder, reviewer]

roles:
  planner: {provider: codex}
  designer: {provider: antigravity, enabled: false} # enable per-run with --with-designer
  coder: {provider: claude}
  reviewer: {provider: codex}

# providers:
#   claude: {command: claude, model: null, timeout_s: 900}
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
NESTED_GITIGNORE = "# AI orchestrator run history (local)\nruns/\n"


def init() -> None:
    """Bootstrap .ai/ in the current directory (config, project profile, gitignore)."""
    project = Path.cwd()
    ai_dir = project / ".ai"
    created: list[str] = []
    skipped: list[str] = []

    (ai_dir / "prompts").mkdir(parents=True, exist_ok=True)

    profile = STARTER_PROFILE.format(stack=detect_stack(project))
    for path, content in (
        (ai_dir / "config.yaml", STARTER_CONFIG),
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
