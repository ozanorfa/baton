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

# A file is a concern if ANY of these trips — not only the blended score.
#
# Why: the composite score averages dimensions, so one severe problem can hide
# behind otherwise clean numbers. Found on a real Flutter project (2026-07-28):
# `snow_world.dart` had **cyclomatic complexity 27**, 26% duplication and no
# tests, yet scored 8.15 — just above the old score-only cutoff, so baton said
# nothing at all. The original 8.0 threshold had been calibrated on one repo
# (baton's own, whose worst file scores 2.4) and did not generalize.
HEALTHY_SCORE = 8.0
CCN_CONCERN = 15  # cyclomatic complexity of the worst function in the file
NESTING_CONCERN = 4
# Duplication is REPORTED but never triggers on its own: a constants/config file
# reads as ~100% duplicated by construction (observed on game_constants.dart,
# score 9.7 — flagging it would push a real hotspot out of a 5-slot list).
DUPLICATION_CONCERN = 20.0  # percent — display threshold only

# repowise scores every file it can read, including markdown, YAML and baton's
# own .ai/ — those are never refactoring targets and they inflate the headline
# ("24 files analyzed" for a project with 8 Dart files). Only real source counts.
_NON_SOURCE_DIRS = (".ai/", ".repowise/", "build/", ".dart_tool/", "node_modules/")


def _is_source(file_path: str) -> bool:
    """True for files that are actual code — the only ones worth flagging."""
    # Imported here, not at module level: context/awareness.py imports this
    # module, so a module-level import back into it would be circular.
    from ai_orchestrator.context.awareness import CODE_EXTENSIONS

    if any(part in file_path for part in _NON_SOURCE_DIRS) or file_path.startswith("."):
        return False
    dot = file_path.rfind(".")
    return dot != -1 and file_path[dot:].lower() in CODE_EXTENSIONS


def _concerns(metric: dict) -> list[str]:
    """Which dimensions make this file a hotspot; empty means it is fine."""
    reasons: list[str] = []
    score = metric.get("score")
    if isinstance(score, (int, float)) and score < HEALTHY_SCORE:
        reasons.append("low overall score")
    ccn = metric.get("max_ccn")
    if isinstance(ccn, int) and ccn >= CCN_CONCERN:
        reasons.append("high complexity")
    nesting = metric.get("max_nesting")
    if isinstance(nesting, int) and nesting >= NESTING_CONCERN:
        reasons.append("deep nesting")
    return reasons


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
    metrics = [
        m for m in (data.get("metrics") or [])
        if isinstance(m.get("score"), (int, float)) and _is_source(m.get("file_path", ""))
    ]
    if not metrics:
        return ""

    # Counted over source files only — repowise's own file_count/average include
    # markdown and config, which made the headline read far healthier than the code.
    avg = sum(m["score"] for m in metrics) / len(metrics)
    ranked = sorted(metrics, key=lambda m: m["score"])
    headline = (
        f"{len(metrics)} source files analyzed · average health {avg:.1f}/10 · "
        f"worst: {ranked[0]['file_path']} ({ranked[0]['score']:.1f}/10)"
    )

    concerns = [(m, r) for m in ranked if (r := _concerns(m))][:WORST_FILES_MAX]
    if not concerns:
        return ""

    rows = []
    for m, reasons in concerns:
        path = m.get("file_path", "?")
        detail = f"score {m['score']:.1f}/10"
        ccn = m.get("max_ccn")
        nest = m.get("max_nesting")
        dup = m.get("duplication_pct")
        if isinstance(ccn, int):
            detail += f", max complexity {ccn}"
        if isinstance(nest, int):
            detail += f", nesting {nest}"
        if isinstance(dup, (int, float)) and dup >= DUPLICATION_CONCERN:
            detail += f", {dup:.0f}% duplication"
        if m.get("has_test_file") is False:
            detail += ", no tests"
        rows.append(f"- `{path}` — {detail} _({', '.join(reasons)})_")

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
