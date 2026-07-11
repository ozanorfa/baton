"""Shared vocabulary of the system (ARCHITECTURE.md §2.2, §3.1).

This module must not import from any other ai_orchestrator module, so every
layer can import it without cycles.
"""

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


def utcnow() -> datetime:
    return datetime.now(UTC)


class StageStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class RunStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class StageSpec(BaseModel):
    """One stage of the pipeline, as configured. Immutable."""

    model_config = ConfigDict(frozen=True)

    name: str
    role: str
    optional: bool = False
    inputs: list[str] = Field(default_factory=list)  # artifact names consumed
    output: str  # artifact name produced


class Usage(BaseModel):
    """Token/cost usage. Fields are None when the provider does not report them —
    values are measured or absent, never estimated (risk R2)."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None


class Capabilities(BaseModel):
    model_config = ConfigDict(frozen=True)

    supports_resume: bool = False
    reports_tokens: bool = False
    edits_files: bool = False


class Health(BaseModel):
    ok: bool
    binary: str | None = None
    version: str | None = None
    authenticated: bool | None = None  # None = not probed
    detail: str = ""


class AgentRequest(BaseModel):
    """What the engine asks a provider to do (one stage invocation)."""

    role: str
    prompt: str
    workdir: Path
    timeout_s: int
    session_id: str | None = None  # for post-MVP resume; recorded from day one


class AgentResult(BaseModel):
    """What came back from a provider, normalized by its adapter."""

    success: bool
    text: str = ""
    session_id: str | None = None
    usage: Usage | None = None
    raw_path: Path | None = None  # full raw output on disk
    error: str | None = None


class StageResult(BaseModel):
    """Per-stage record inside RunState; persisted in run.json on every transition."""

    name: str
    role: str
    status: StageStatus = StageStatus.PENDING
    provider: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    artifact: str | None = None  # artifact name, resolvable within the run dir
    session_id: str | None = None
    usage: Usage | None = None
    error: str | None = None

    @property
    def duration_s(self) -> float | None:
        if self.started_at is None or self.finished_at is None:
            return None
        return (self.finished_at - self.started_at).total_seconds()


class RunState(BaseModel):
    """The run state machine, serialized as run.json (ARCHITECTURE §2.4)."""

    run_id: str
    request: str
    project_dir: Path
    created_at: datetime = Field(default_factory=utcnow)
    status: RunStatus = RunStatus.RUNNING
    stages: list[StageResult] = Field(default_factory=list)

    def stage(self, name: str) -> StageResult:
        for s in self.stages:
            if s.name == name:
                return s
        raise KeyError(f"no stage named {name!r} in run {self.run_id}")
