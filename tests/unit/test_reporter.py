import json
from pathlib import Path

from ai_orchestrator.core.models import (
    RunStatus,
    StageSpec,
    StageStatus,
    Usage,
    utcnow,
)
from ai_orchestrator.core.reporter import save_report
from ai_orchestrator.core.run_manager import RunManager

SPECS = [
    StageSpec(name="planner", role="planner", output="plan.md"),
    StageSpec(name="coder", role="coder", inputs=["plan.md"], output="changes.md"),
    StageSpec(name="reviewer", role="reviewer", inputs=["plan.md"], output="review.md"),
]


def make_run(tmp_path: Path, with_review: bool = True):
    manager = RunManager(tmp_path)
    state = manager.create_run("add feature", SPECS)
    t0 = utcnow()
    for i, stage in enumerate(state.stages):
        stage.status = StageStatus.SUCCEEDED
        stage.provider = "prov"
        stage.started_at = t0
        stage.finished_at = t0
        stage.artifact = state.stages[i].name + ".md"
    state.status = RunStatus.SUCCEEDED
    state.stages[0].usage = Usage(input_tokens=100, output_tokens=10)
    state.stages[1].usage = Usage(input_tokens=200, output_tokens=20, cost_usd=0.5)
    # reviewer usage stays None (e.g. antigravity)
    if with_review:
        manager.save_artifact(state, "review.md", "**Verdict** — APPROVE WITH NOTES\n\nFine.")
    manager.save(state)
    return state, manager


def test_report_totals_and_verdict(tmp_path: Path) -> None:
    state, manager = make_run(tmp_path)
    report = save_report(state, manager)

    assert report.total_input_tokens == 300  # only measured values summed
    assert report.total_output_tokens == 30
    assert report.total_cost_usd == 0.5
    assert report.verdict == "APPROVE WITH NOTES"
    assert report.wall_duration_s == 0.0
    assert report.status == "succeeded"


def test_report_json_uses_null_never_zero(tmp_path: Path) -> None:
    state, manager = make_run(tmp_path)
    save_report(state, manager)
    data = json.loads((manager.run_dir(state.run_id) / "report.json").read_text(encoding="utf-8"))

    reviewer = data["stages"][2]
    assert reviewer["input_tokens"] is None  # unmeasured → null, not 0
    assert reviewer["cost_usd"] is None
    assert data["total_cost_usd"] == 0.5


def test_report_failed_run_without_review(tmp_path: Path) -> None:
    state, manager = make_run(tmp_path, with_review=False)
    state.stages[2].status = StageStatus.FAILED
    state.stages[2].error = "boom"
    report = save_report(state, manager)
    assert report.verdict is None
    assert report.stages[2].error == "boom"


def test_verdict_variants(tmp_path: Path) -> None:
    state, manager = make_run(tmp_path, with_review=False)
    manager.save_artifact(state, "review.md", "## Review\n\n1. **Verdict** — NEEDS WORK\n")
    assert save_report(state, manager).verdict == "NEEDS WORK"
    manager.save_artifact(state, "review.md", "Verdict: APPROVE\n")
    assert save_report(state, manager).verdict == "APPROVE"


def test_review_findings_counts_by_severity_within_the_findings_section() -> None:
    from ai_orchestrator.core.reporter import review_findings

    review = (
        "1. **Verdict** — NEEDS WORK\n\n"
        "2. **Verification performed** — ran the major test suite\n\n"  # 'major' outside Findings
        "3. **Findings**\n"
        "   1. blocker — src/a.py: crashes on empty input\n"
        "   2. major — src/b.py: n+1 query\n"
        "   3. minor — naming\n"
        "   4. minor — typo\n\n"
        "4. **Suggestions** — a minor restructure later (blocker-free)\n"
    )
    assert review_findings(review) == {"blocker": 1, "major": 1, "minor": 2}
    assert review_findings("") == {"blocker": 0, "major": 0, "minor": 0}


def test_diff_stats_counts_files_and_lines_not_headers() -> None:
    from ai_orchestrator.core.reporter import diff_stats

    patch = (
        "diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n@@ -1,2 +1,3 @@\n"
        "-old\n+new\n+more\n"
        "diff --git a/y.py b/y.py\nnew file mode 100644\n--- /dev/null\n+++ b/y.py\n"
        "@@ -0,0 +1 @@\n+hello\n"
    )
    assert diff_stats(patch) == (2, 3, 1)
    assert diff_stats("") == (0, 0, 0)
