"""Reporter (ARCHITECTURE.md §2.5): aggregates a finished run into report.json.

Token/cost figures are copied from what providers measured; absent values
stay null — never estimated (risk R2). The verdict is parsed from the
reviewer's artifact when present.
"""

import re
from datetime import datetime

from pydantic import BaseModel

from ai_orchestrator.core.models import RunState, StageStatus
from ai_orchestrator.core.run_manager import RunManager

VERDICT_PATTERN = re.compile(r"Verdict\W{0,10}(APPROVE WITH NOTES|APPROVE|NEEDS WORK)")


class StageReport(BaseModel):
    name: str
    provider: str | None
    status: StageStatus
    duration_s: float | None
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: float | None
    artifact: str | None
    session_id: str | None
    error: str | None


COST_NOTE = (
    "cost figures are the provider-reported API-equivalent value; on "
    "subscription plans they consume plan quota — no per-run charge"
)


class Report(BaseModel):
    run_id: str
    request: str
    status: str
    created_at: datetime
    wall_duration_s: float | None  # first stage start → last stage finish
    total_input_tokens: int | None  # sum of measured values; null if none measured
    total_output_tokens: int | None
    total_cost_usd: float | None
    cost_note: str = COST_NOTE
    verdict: str | None  # parsed from review.md when present
    stages: list[StageReport]


def _total(values: list[int | float | None]) -> int | float | None:
    measured = [v for v in values if v is not None]
    return sum(measured) if measured else None


def build_report(state: RunState, run_manager: RunManager) -> Report:
    verdict = None
    review_path = run_manager.artifacts_dir(state.run_id) / "review.md"
    if review_path.is_file():
        match = VERDICT_PATTERN.search(review_path.read_text())
        if match:
            verdict = match.group(1)

    starts = [s.started_at for s in state.stages if s.started_at]
    ends = [s.finished_at for s in state.stages if s.finished_at]
    wall = (max(ends) - min(starts)).total_seconds() if starts and ends else None

    stages = [
        StageReport(
            name=s.name,
            provider=s.provider,
            status=s.status,
            duration_s=s.duration_s,
            input_tokens=s.usage.input_tokens if s.usage else None,
            output_tokens=s.usage.output_tokens if s.usage else None,
            cost_usd=s.usage.cost_usd if s.usage else None,
            artifact=s.artifact,
            session_id=s.session_id,
            error=s.error,
        )
        for s in state.stages
    ]
    return Report(
        run_id=state.run_id,
        request=state.request,
        status=state.status.value,
        created_at=state.created_at,
        wall_duration_s=wall,
        total_input_tokens=_total([s.input_tokens for s in stages]),
        total_output_tokens=_total([s.output_tokens for s in stages]),
        total_cost_usd=_total([s.cost_usd for s in stages]),
        verdict=verdict,
        stages=stages,
    )


def save_report(state: RunState, run_manager: RunManager) -> Report:
    report = build_report(state, run_manager)
    path = run_manager.run_dir(state.run_id) / "report.json"
    path.write_text(report.model_dump_json(indent=2))
    return report
