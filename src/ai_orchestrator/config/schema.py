"""Typed configuration (ARCHITECTURE.md §4).

Unknown keys are tolerated with a warning (forward compatibility); invalid
values fail fast. The loader (loader.py) attaches file/source information to
validation errors.
"""

import warnings

from pydantic import BaseModel, ConfigDict, Field, model_validator

_LENIENT = ConfigDict(extra="allow")


class PipelineConfig(BaseModel):
    model_config = _LENIENT

    stages: list[str] = Field(min_length=1)
    # ADR-015: when two stages share a provider (default: planner/reviewer/
    # publisher are all Codex), the later one resumes the earlier one's
    # session instead of cold-starting. Cuts redundant repo re-exploration.
    # Trade-off: the resumed stage inherits the earlier stage's transcript,
    # a deliberate exception to ADR-006 for same-provider stages only.
    # Per-project opt-out: pipeline: {session_chaining: false}
    session_chaining: bool = True
    # ADR-023: when the Reviewer returns NEEDS WORK (a blocking finding), run
    # exactly one automatic fix pass — re-run the Coder with the review findings,
    # then re-review, then stop. Off by default (an extra Coder+Reviewer turn
    # costs quota); opt in per project or with `ai run --fix-loop`.
    fix_loop: bool = False


class RoleConfig(BaseModel):
    model_config = _LENIENT

    provider: str
    enabled: bool = True


class ProviderConfig(BaseModel):
    model_config = _LENIENT

    command: str
    model: str | None = None
    timeout_s: int = Field(default=600, gt=0)


class ContextConfig(BaseModel):
    model_config = _LENIENT

    project_profile: str = ".ai/project.md"


class AppConfig(BaseModel):
    model_config = _LENIENT

    pipeline: PipelineConfig
    roles: dict[str, RoleConfig]
    providers: dict[str, ProviderConfig]
    context: ContextConfig = Field(default_factory=ContextConfig)

    @model_validator(mode="after")
    def _cross_check(self) -> "AppConfig":
        for stage in self.pipeline.stages:
            if stage not in self.roles:
                raise ValueError(
                    f"pipeline stage {stage!r} has no entry under 'roles' "
                    f"(defined roles: {sorted(self.roles)})"
                )
        for role_name, role in self.roles.items():
            if role.provider not in self.providers:
                raise ValueError(
                    f"role {role_name!r} is bound to unknown provider {role.provider!r} "
                    f"(defined providers: {sorted(self.providers)})"
                )
        return self


def warn_unknown_keys(model: BaseModel, source: str, path: str = "") -> list[str]:
    """Recursively warn about keys not defined in the schema. Returns the paths found."""
    found: list[str] = []
    extra = model.model_extra or {}
    for key in extra:
        found.append(f"{path}{key}")
    for name in type(model).model_fields:
        value = getattr(model, name)
        if isinstance(value, dict):
            children = list(value.values())
        elif isinstance(value, list):
            children = value
        else:
            children = [value]
        for child in children:
            if isinstance(child, BaseModel):
                found.extend(warn_unknown_keys(child, source, f"{path}{name}."))
    if path == "" and found:
        warnings.warn(
            f"unknown config keys in {source}: {', '.join(sorted(found))}",
            stacklevel=2,
        )
    return found
