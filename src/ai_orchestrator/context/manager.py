"""ContextManager (ARCHITECTURE.md §5): assembles the four layers into the
prompt for one stage. This is the only place prompts are built — replacing
the naive M2 stub in core/engine.py.

Matches the engine's PromptBuilder signature, so wiring is one argument:
    PipelineEngine(manager, transport, prompt_builder=ContextManager(...).build)
"""

from pathlib import Path

from ai_orchestrator.context.awareness import workspace_layer
from ai_orchestrator.context.contracts import contract_for
from ai_orchestrator.context.layers import (
    agent_template,
    global_layer,
    inputs_section,
    project_layer,
)
from ai_orchestrator.core.models import StageSpec


class ContextManager:
    def __init__(
        self,
        project_dir: Path,
        profile_relpath: str = ".ai/project.md",
        include_health: bool = False,
    ):
        self.project_dir = project_dir
        self.profile_relpath = profile_relpath
        # Computed once per run, not per stage — the workspace doesn't change
        # between stages (the coder's edits notwithstanding; orientation is
        # a starting map, not a live view). This is also why the opt-in repowise
        # health probe runs at most once per run, not once per stage.
        self._workspace = workspace_layer(project_dir, include_health=include_health)

    def build(self, spec: StageSpec, request: str, artifacts: dict[str, str]) -> str:
        contract = contract_for(spec.role)  # template/boundaries by role
        template = agent_template(contract, self.project_dir)
        prompt = template.safe_substitute(
            role=spec.role,
            global_rules=global_layer(),
            project_context=project_layer(self.project_dir, self.profile_relpath),
            workspace=self._workspace,
            request=request,
            # admitted inputs come from the spec (contract-derived at routing time,
            # incl. generic chain contracts for unknown roles)
            inputs=inputs_section(spec.inputs, artifacts),
        )
        return prompt.strip() + "\n"
