"""The four context layers (ARCHITECTURE.md §5).

Global  — orchestrator conventions, static (prompts/_global.md)
Project — the project's profile (.ai/project.md, written by `ai init`)
Task    — the request + contract-admitted artifacts (assembled in manager.py)
Agent   — the role's prompt template (built-in, overridable per project)
"""

from collections.abc import Iterable
from importlib.resources import files
from pathlib import Path
from string import Template

from ai_orchestrator.context.contracts import RoleContract

_PROMPTS = files("ai_orchestrator.prompts")

NO_PROFILE_NOTE = (
    "## Project context\n\n"
    "(No project profile found. Infer conventions from the codebase itself; "
    "run `ai init` in this project to provide one.)"
)


def global_layer() -> str:
    return (_PROMPTS / "_global.md").read_text().strip()


def project_layer(project_dir: Path, profile_relpath: str) -> str:
    profile = project_dir / profile_relpath
    if profile.is_file() and profile.read_text().strip():
        return f"## Project context\n\n{profile.read_text().strip()}"
    return NO_PROFILE_NOTE


def agent_template(contract: RoleContract, project_dir: Path) -> Template:
    """Project override (.ai/prompts/<template>) wins over the built-in (ADR-009)."""
    override = project_dir / ".ai" / "prompts" / contract.template
    if override.is_file():
        return Template(override.read_text())
    return Template((_PROMPTS / contract.template).read_text())


def inputs_section(admitted: Iterable[str], artifacts: dict[str, str]) -> str:
    """Only contract-admitted artifacts, in contract order. Artifacts from
    skipped stages are simply absent — no placeholder noise."""
    sections = [
        f"## Input from a previous stage: {name}\n\n{artifacts[name].strip()}"
        for name in admitted
        if name in artifacts
    ]
    return "\n\n".join(sections)
