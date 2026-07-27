"""Repo health context (repowise) — optional, zero-LLM code-intelligence layer.

Shells out to `repowise health --format json`. That command is in-process in
repowise (no LLM, no network — verified live 2026-07-27) and works with no
prior `repowise init`. We render a compact KPI + worst-files slice for stage
prompts, telling the model which existing files are complexity hotspots before
it plans/edits/reviews them.

Design guarantees (see IDEAS.md item 2):
  * Entirely optional. If the `repowise` binary is absent, or the call fails,
    times out, or returns unparseable output, `health_section` returns "" and
    the prompt is byte-identical to before — never a hard dependency.
  * We only ever run `repowise health`, never `repowise init` — `init` performs
    machine-wide config writes (global MCP server + hooks) and can spend LLM
    tokens; it stays a human-triggered, one-time step, always.
  * The formatter (`render_health`) is pure and deterministic, so it is unit
    testable against recorded JSON without invoking repowise.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

# repowise health writes a ~1 MB index here on first run. We only ever run
# `health` when the user has NOT set repowise up themselves, so baton must not
# leave litter in their tree — we remove this dir iff we were the one to create
# it (it was absent before the call). A pre-existing .repowise/ is the user's
# and is never touched.
_INDEX_DIR = ".repowise"

HEALTH_TIMEOUT_S = 30
# Only the worst few files earn prompt space — the full metrics array is ~25k
# tokens on a 113-file repo (measured); the point is a bounded slice, not a dump.
WORST_FILES_MAX = 5
# Files at or above this health score are fine; never list them as concerns.
HEALTHY_SCORE = 8.0


def _run_health(project_dir: Path) -> dict | None:
    """Run `repowise health --format json`; return parsed dict or None on any failure.

    Cleans up the `.repowise/` index iff this call created it (a pre-existing one
    belongs to the user and is left untouched).
    """
    exe = shutil.which("repowise")
    if exe is None:
        return None
    index_preexisted = (project_dir / _INDEX_DIR).exists()
    try:
        proc = subprocess.run(
            [exe, "health", str(project_dir), "--format", "json"],
            capture_output=True,
            text=True,
            timeout=HEALTH_TIMEOUT_S,
            cwd=str(project_dir),
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    finally:
        _cleanup_index(project_dir, index_preexisted)
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    try:
        parsed = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _cleanup_index(project_dir: Path, index_preexisted: bool) -> None:
    """Remove the .repowise/ index only if we created it this call."""
    if index_preexisted:
        return
    created = project_dir / _INDEX_DIR
    if created.exists():
        shutil.rmtree(created, ignore_errors=True)


def render_health(data: dict) -> str:
    """Pure formatter: KPI headline + the worst-scoring files. "" if nothing useful.

    Deterministic and side-effect-free so it can be unit tested against recorded
    repowise JSON without a live install.
    """
    kpis = data.get("kpis") or {}
    metrics = data.get("metrics") or []
    if not kpis or not metrics:
        return ""

    file_count = kpis.get("file_count")
    avg = kpis.get("average_health")
    worst_path = kpis.get("worst_performer_path")
    worst_score = kpis.get("worst_performer_score")

    headline_bits = []
    if isinstance(file_count, int):
        headline_bits.append(f"{file_count} files analyzed")
    if isinstance(avg, (int, float)):
        headline_bits.append(f"average health {avg:.1f}/10")
    if worst_path and isinstance(worst_score, (int, float)):
        headline_bits.append(f"worst: {worst_path} ({worst_score:.1f}/10)")
    headline = " · ".join(headline_bits)

    # Worst files first; only those actually below the healthy bar are worth naming.
    ranked = sorted(
        (m for m in metrics if isinstance(m.get("score"), (int, float))),
        key=lambda m: m["score"],
    )
    concerns = [m for m in ranked if m["score"] < HEALTHY_SCORE][:WORST_FILES_MAX]
    if not concerns:
        return ""

    rows = []
    for m in concerns:
        path = m.get("file_path", "?")
        score = m.get("score")
        ccn = m.get("max_ccn")
        nest = m.get("max_nesting")
        test = "no tests" if m.get("has_test_file") is False else ""
        detail = f"score {score:.1f}/10"
        if isinstance(ccn, int):
            detail += f", max complexity {ccn}"
        if isinstance(nest, int):
            detail += f", nesting {nest}"
        if test:
            detail += f", {test}"
        rows.append(f"- `{path}` — {detail}")

    lines = [
        "### Code-health hotspots (repowise, static analysis)",
        (
            "These existing files are the most complex/risky in the repo. If your "
            "change touches one, treat it with extra care (smaller edits, more "
            "tests, prefer reducing complexity over adding to it):"
        ),
    ]
    if headline:
        lines.insert(1, f"_{headline}._")
    lines.append("\n".join(rows))
    return "\n\n".join(lines)


def health_section(project_dir: Path) -> str:
    """The optional health slice for a stage prompt, or "" if unavailable.

    Safe to call unconditionally: returns "" when repowise is not installed or
    the analysis yields nothing worth surfacing.
    """
    data = _run_health(project_dir)
    if data is None:
        return ""
    return render_health(data)
