"""`ai init` — bootstrap .ai/ in a project (PROJECT_STRUCTURE.md §2.1).

Idempotent: existing files are never overwritten, only reported. `.ai/runs/`
is gitignored (local history); config.yaml and project.md are meant to be
committed and shared with the team.
"""

from pathlib import Path

from ai_orchestrator.cli import render

STARTER_CONFIG = """\
# AI Orchestrator — project configuration (commit this file)
# Anything omitted falls back to user config (~/.config/ai-orchestrator/config.yaml)
# and built-in defaults. `ai config show` prints the merged result with sources.

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

<!-- e.g.: Flutter 3.x app. State management: Riverpod. Backend: Firebase. -->

## Structure & conventions

<!-- e.g.: feature-first layout under lib/features/. Tests mirror lib/ in test/.
     Naming: snake_case files, English identifiers. -->

## Things AI assistants get wrong in this project

<!-- e.g.: don't suggest setState — this project uses Riverpod everywhere. -->
"""

GITIGNORE_ENTRY = ".ai/runs/"


def init() -> None:
    """Bootstrap .ai/ in the current directory (config, project profile, gitignore)."""
    project = Path.cwd()
    ai_dir = project / ".ai"
    created: list[str] = []
    skipped: list[str] = []

    (ai_dir / "prompts").mkdir(parents=True, exist_ok=True)

    for path, content in (
        (ai_dir / "config.yaml", STARTER_CONFIG),
        (ai_dir / "project.md", STARTER_PROFILE),
    ):
        rel = str(path.relative_to(project))
        if path.exists():
            skipped.append(rel)
        else:
            path.write_text(content)
            created.append(rel)

    gitignore = project / ".gitignore"
    if gitignore.exists():
        if GITIGNORE_ENTRY in gitignore.read_text():
            skipped.append(f".gitignore ({GITIGNORE_ENTRY} already present)")
        else:
            with gitignore.open("a") as f:
                f.write(f"\n# AI orchestrator run history (local)\n{GITIGNORE_ENTRY}\n")
            created.append(f".gitignore (+ {GITIGNORE_ENTRY})")
    else:
        gitignore.write_text(f"# AI orchestrator run history (local)\n{GITIGNORE_ENTRY}\n")
        created.append(f".gitignore (+ {GITIGNORE_ENTRY})")

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
