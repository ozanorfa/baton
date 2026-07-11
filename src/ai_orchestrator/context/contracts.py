"""Per-stage input contracts (ARCHITECTURE.md §5) — data, not logic.

The single source of truth for what each role consumes, produces, and may
touch. A contract change is a one-line diff with an obvious review surface.
This is the enforcement point of the minimal-context principle (risk R4):
a stage can only ever receive the artifacts its contract admits.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class RoleContract:
    role: str
    inputs: tuple[str, ...]  # artifact names this role may receive
    output: str  # artifact name this role produces
    allow_edits: bool  # may this role modify the repository? (ADR-007)
    template: str  # prompt template filename (in prompts/, overridable per project)


CONTRACTS: dict[str, RoleContract] = {
    "planner": RoleContract(
        role="planner", inputs=(), output="plan.md",
        allow_edits=False, template="planner.md",
    ),
    "designer": RoleContract(
        role="designer", inputs=("plan.md",), output="design.md",
        allow_edits=False, template="designer.md",
    ),
    "coder": RoleContract(
        role="coder", inputs=("plan.md", "design.md"), output="changes.md",
        allow_edits=True, template="coder.md",
    ),
    "reviewer": RoleContract(
        role="reviewer", inputs=("plan.md", "changes.md", "diff.patch"), output="review.md",
        allow_edits=False, template="reviewer.md",
    ),
}


def contract_for(role: str, previous_output: str | None = None) -> RoleContract:
    """Known roles get their contract; unknown roles get a generic chain
    contract (consume the previous stage's artifact, produce <role>.md)."""
    known = CONTRACTS.get(role)
    if known is not None:
        return known
    return RoleContract(
        role=role,
        inputs=(previous_output,) if previous_output else (),
        output=f"{role}.md",
        allow_edits=False,
        template="_generic.md",
    )
