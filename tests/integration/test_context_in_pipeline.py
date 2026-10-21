"""T23: the layered context system in a real pipeline run — every persisted
prompt contains exactly what its role's contract admits, nothing more."""

from pathlib import Path

from ai_orchestrator.config.loader import load_config
from ai_orchestrator.context.manager import ContextManager
from ai_orchestrator.core.engine import PipelineEngine
from ai_orchestrator.core.models import RunStatus
from ai_orchestrator.core.routing import RoutingEngine, build_stage_specs
from ai_orchestrator.core.run_manager import RunManager
from ai_orchestrator.transport.headless import HeadlessTransport

FAKE_CLI = Path(__file__).parent / "fake_provider" / "fake_ai.py"


def full_fake_project(tmp_path: Path, monkeypatch) -> Path:
    """All four stages (designer enabled) on the fake provider, with a
    project profile and a per-project template override for the planner."""
    project = tmp_path / "proj4"
    (project / ".ai" / "prompts").mkdir(parents=True)
    (project / ".ai" / "config.yaml").write_text(
        "pipeline:\n  stages: [planner, designer, coder, reviewer]\n"
        "roles:\n"
        "  planner: {provider: fake}\n"
        "  designer: {provider: fake, enabled: true}\n"
        "  coder: {provider: fake}\n"
        "  reviewer: {provider: fake}\n"
        "providers:\n"
        f"  fake: {{command: {FAKE_CLI}, timeout_s: 30}}\n", encoding="utf-8")
    (project / ".ai" / "project.md").write_text("STACK-MARKER: Flutter 9.9 with TestState",
        encoding="utf-8")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    return project


def test_prompts_respect_contracts_and_layers(tmp_path, fake_registry, monkeypatch) -> None:
    project = full_fake_project(tmp_path, monkeypatch)
    loaded = load_config(project, env={})
    transport = HeadlessTransport()
    resolved = RoutingEngine(loaded.config, fake_registry).resolve(
        build_stage_specs(loaded.config), transport
    )
    manager = RunManager(project)
    context = ContextManager(project, loaded.config.context.project_profile)
    state = PipelineEngine(manager, transport, prompt_builder=context.build).execute(
        "add a settings screen", resolved
    )
    assert state.status is RunStatus.SUCCEEDED

    prompts_dir = manager.run_dir(state.run_id) / "prompts"
    planner = (prompts_dir / "01-planner.md").read_text(encoding="utf-8")
    designer = (prompts_dir / "02-designer.md").read_text(encoding="utf-8")
    coder = (prompts_dir / "03-coder.md").read_text(encoding="utf-8")
    reviewer = (prompts_dir / "04-reviewer.md").read_text(encoding="utf-8")

    plan_output = manager.load_artifact(state, "plan.md").strip()
    design_output = manager.load_artifact(state, "design.md").strip()
    changes_output = manager.load_artifact(state, "changes.md").strip()

    # role templates present, with boundaries
    assert "# Role: Planner" in planner and "plan only" in planner
    assert "# Role: Reviewer" in reviewer and "do NOT rewrite the code" in reviewer

    # every stage gets the global rules and the project layer
    for prompt in (planner, designer, coder, reviewer):
        assert "## Working rules (all roles)" in prompt
        assert "STACK-MARKER: Flutter 9.9" in prompt
        assert "add a settings screen" in prompt

    # contract enforcement: exactly the admitted inputs, nothing more
    assert "Input from a previous stage" not in planner
    assert plan_output in designer
    assert plan_output in coder and design_output in coder
    assert plan_output in reviewer and changes_output in reviewer
    assert design_output not in reviewer  # design is NOT in the reviewer's contract


def test_project_template_override_used_in_run(tmp_path, fake_registry, monkeypatch) -> None:
    project = full_fake_project(tmp_path, monkeypatch)
    (project / ".ai" / "prompts" / "planner.md").write_text(
        "OVERRIDDEN PLANNER TEMPLATE\n\n$request\n", encoding="utf-8")
    loaded = load_config(project, env={})
    transport = HeadlessTransport()
    resolved = RoutingEngine(loaded.config, fake_registry).resolve(
        build_stage_specs(loaded.config), transport
    )
    manager = RunManager(project)
    context = ContextManager(project, loaded.config.context.project_profile)
    state = PipelineEngine(manager, transport, prompt_builder=context.build).execute(
        "anything", resolved
    )
    planner = (manager.run_dir(state.run_id) / "prompts" / "01-planner.md").read_text(
        encoding="utf-8"
    )
    assert planner.startswith("OVERRIDDEN PLANNER TEMPLATE")
    assert "# Role: Planner" not in planner
