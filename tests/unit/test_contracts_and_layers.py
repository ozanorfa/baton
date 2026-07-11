from pathlib import Path

from ai_orchestrator.context.contracts import CONTRACTS, contract_for
from ai_orchestrator.context.layers import (
    NO_PROFILE_NOTE,
    agent_template,
    global_layer,
    inputs_section,
    project_layer,
)


def test_contract_table_matches_architecture_doc() -> None:
    # the ARCHITECTURE §5 table as executable assertions
    assert contract_for("planner").inputs == ()
    assert contract_for("designer").inputs == ("plan.md",)
    assert contract_for("coder").inputs == ("plan.md", "design.md")
    assert contract_for("reviewer").inputs == ("plan.md", "changes.md")
    assert [c.allow_edits for c in CONTRACTS.values()] == [False, False, True, False]


def test_unknown_role_gets_generic_chain_contract() -> None:
    c = contract_for("tester", previous_output="review.md")
    assert c.inputs == ("review.md",)
    assert c.output == "tester.md"
    assert not c.allow_edits
    assert c.template == "_generic.md"


def test_inputs_section_admits_only_contract_artifacts() -> None:
    artifacts = {
        "plan.md": "THE PLAN",
        "design.md": "THE DESIGN",
        "changes.md": "THE CHANGES",
        "secret.md": "NOT FOR YOU",
    }
    reviewer = inputs_section(contract_for("reviewer"), artifacts)
    assert "THE PLAN" in reviewer and "THE CHANGES" in reviewer
    assert "THE DESIGN" not in reviewer  # not in the reviewer's contract
    assert "NOT FOR YOU" not in reviewer


def test_inputs_section_skips_absent_artifacts_silently() -> None:
    # designer disabled → coder receives plan only, no placeholder noise
    coder = inputs_section(contract_for("coder"), {"plan.md": "P"})
    assert "plan.md" in coder and "design.md" not in coder


def test_project_layer_reads_profile_or_notes_absence(tmp_path: Path) -> None:
    assert project_layer(tmp_path, ".ai/project.md") == NO_PROFILE_NOTE
    (tmp_path / ".ai").mkdir()
    (tmp_path / ".ai" / "project.md").write_text("Flutter 3.x, Riverpod")
    assert "Flutter 3.x, Riverpod" in project_layer(tmp_path, ".ai/project.md")


def test_agent_template_project_override_wins(tmp_path: Path) -> None:
    built_in = agent_template(contract_for("planner"), tmp_path).template
    assert "Role: Planner" in built_in
    (tmp_path / ".ai" / "prompts").mkdir(parents=True)
    (tmp_path / ".ai" / "prompts" / "planner.md").write_text("CUSTOM $request")
    assert agent_template(contract_for("planner"), tmp_path).template == "CUSTOM $request"


def test_all_builtin_templates_exist_and_carry_placeholders() -> None:
    for contract in CONTRACTS.values():
        text = agent_template(contract, Path("/nonexistent")).template
        for placeholder in ("$global_rules", "$project_context", "$request", "$inputs"):
            assert placeholder in text, f"{contract.template} missing {placeholder}"
    assert global_layer().startswith("## Working rules")
