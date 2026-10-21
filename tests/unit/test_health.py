"""Unit tests for the repowise health context layer (context/health.py).

The formatter is pure, so it is tested against recorded repowise JSON with no
live install. The gathering path is tested for its guarantee: any failure
(missing binary, bad exit, unparseable output) yields "" — never an exception.
"""

from pathlib import Path

from ai_orchestrator.context import health as H

# A trimmed but real-shaped `repowise health --format json` payload
# (keys captured live from repowise 0.34.0, 2026-07-27).
SAMPLE = {
    "kpis": {
        "hotspot_health": 5.63,
        "average_health": 8.77,
        "worst_performer_path": "src/core/engine.py",
        "worst_performer_score": 2.36,
        "file_count": 113,
    },
    "metrics": [
        {"file_path": "src/core/engine.py", "score": 2.36, "max_ccn": 26,
         "max_nesting": 4, "nloc": 200, "has_test_file": True},
        {"file_path": "src/cli/render.py", "score": 3.0, "max_ccn": 17,
         "max_nesting": 3, "nloc": 120, "has_test_file": False},
        {"file_path": "src/simple.py", "score": 10.0, "max_ccn": 1,
         "max_nesting": 0, "nloc": 3, "has_test_file": True},
    ],
    "findings": [],
}


def test_render_lists_only_unhealthy_files() -> None:
    out = H.render_health(SAMPLE)
    assert "src/core/engine.py" in out
    assert "src/cli/render.py" in out
    # A healthy (10/10) file is never named as a concern.
    assert "src/simple.py" not in out


def test_render_includes_headline_and_metrics() -> None:
    out = H.render_health(SAMPLE)
    # The headline counts SOURCE files only — repowise's own file_count includes
    # markdown/YAML, which made the numbers read healthier than the code (ADR-025
    # amendment, 2026-07-28).
    assert "source files analyzed" in out
    assert "max complexity 26" in out
    assert "no tests" in out  # render.py has_test_file is False


def test_render_caps_worst_files() -> None:
    many = {
        "kpis": {"file_count": 20, "average_health": 4.0,
                 "worst_performer_path": "a0.py", "worst_performer_score": 1.0},
        "metrics": [
            {"file_path": f"a{i}.py", "score": float(i) / 10, "max_ccn": 5,
             "max_nesting": 2, "has_test_file": True}
            for i in range(20)
        ],
        "findings": [],
    }
    out = H.render_health(many)
    listed = [ln for ln in out.splitlines() if ln.startswith("- `")]
    assert len(listed) == H.WORST_FILES_MAX


def test_render_empty_when_all_healthy() -> None:
    allgood = {
        "kpis": {"file_count": 2, "average_health": 10.0,
                 "worst_performer_path": "a.py", "worst_performer_score": 10.0},
        "metrics": [
            {"file_path": "a.py", "score": 10.0, "max_ccn": 1, "has_test_file": True},
            {"file_path": "b.py", "score": 9.0, "max_ccn": 2, "has_test_file": True},
        ],
        "findings": [],
    }
    assert H.render_health(allgood) == ""


def test_render_empty_on_missing_sections() -> None:
    assert H.render_health({}) == ""
    assert H.render_health({"kpis": {}, "metrics": []}) == ""


def test_health_section_empty_when_binary_absent(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(H.shutil, "which", lambda _: None)
    assert H.health_section(tmp_path) == ""


def test_health_section_empty_on_bad_exit(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(H.shutil, "which", lambda _: "/usr/bin/repowise")

    class _Proc:
        returncode = 1
        stdout = ""
        stderr = "boom"

    monkeypatch.setattr(H.subprocess, "run", lambda *a, **k: _Proc())
    assert H.health_section(tmp_path) == ""


def test_health_section_empty_on_unparseable(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(H.shutil, "which", lambda _: "/usr/bin/repowise")

    class _Proc:
        returncode = 0
        stdout = "not json at all"
        stderr = ""

    monkeypatch.setattr(H.subprocess, "run", lambda *a, **k: _Proc())
    assert H.health_section(tmp_path) == ""


def test_health_section_survives_timeout(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(H.shutil, "which", lambda _: "/usr/bin/repowise")

    def _boom(*a, **k):
        raise H.subprocess.TimeoutExpired(cmd="repowise", timeout=H.HEALTH_TIMEOUT_S)

    monkeypatch.setattr(H.subprocess, "run", _boom)
    assert H.health_section(tmp_path) == ""


def test_cleanup_removes_index_we_created(tmp_path: Path) -> None:
    idx = tmp_path / H._INDEX_DIR
    idx.mkdir()
    (idx / "wiki.db").write_text("x", encoding="utf-8")
    H._cleanup_index(tmp_path, index_preexisted=False)
    assert not idx.exists()


def test_cleanup_preserves_users_own_index(tmp_path: Path) -> None:
    idx = tmp_path / H._INDEX_DIR
    idx.mkdir()
    (idx / "wiki.db").write_text("x", encoding="utf-8")
    H._cleanup_index(tmp_path, index_preexisted=True)
    assert idx.exists()  # never touch a pre-existing, user-created index


def test_run_health_cleans_up_after_success(tmp_path: Path, monkeypatch) -> None:
    """A fresh call that creates .repowise/ must leave the tree as it found it."""
    monkeypatch.setattr(H.shutil, "which", lambda _: "/usr/bin/repowise")

    class _Proc:
        returncode = 0
        stdout = "{}"
        stderr = ""

    def _fake_run(*a, **k):
        (tmp_path / H._INDEX_DIR).mkdir()  # mimic repowise writing its index
        return _Proc()

    monkeypatch.setattr(H.subprocess, "run", _fake_run)
    H._run_health(tmp_path)
    assert not (tmp_path / H._INDEX_DIR).exists()


# ── ADR-025 amendment (2026-07-28): a single bad dimension is enough ─────────

def test_high_complexity_is_flagged_even_with_a_healthy_score() -> None:
    """The real-world miss: score-only gating stayed silent on a ccn-27 file.

    Live case (skii_game, a Flutter project): `snow_world.dart` scored 8.15 —
    above the 8.0 cutoff — with cyclomatic complexity 27 and no tests, so baton
    injected nothing at all. The composite score averaged the problem away.
    """
    data = {
        "kpis": {},
        "metrics": [
            {"file_path": "lib/world.dart", "score": 8.15, "max_ccn": 27,
             "max_nesting": 3, "has_test_file": False, "duplication_pct": 26.0},
            {"file_path": "lib/clean.dart", "score": 9.9, "max_ccn": 2,
             "max_nesting": 1, "has_test_file": True},
        ],
    }
    out = H.render_health(data)
    assert "lib/world.dart" in out
    assert "high complexity" in out
    assert "lib/clean.dart" not in out, "a genuinely clean file is still never named"


def test_deep_nesting_alone_is_flagged() -> None:
    data = {"kpis": {}, "metrics": [
        {"file_path": "a.py", "score": 9.0, "max_ccn": 3, "max_nesting": 5},
    ]}
    assert "deep nesting" in H.render_health(data)


def test_duplication_alone_never_flags_a_file() -> None:
    """A constants file reads as ~100% duplicated by construction.

    Observed on `game_constants.dart` (score 9.7, 100% duplication): treating
    that as a hotspot would evict a real one from the five-slot list.
    """
    data = {"kpis": {}, "metrics": [
        {"file_path": "constants.py", "score": 9.7, "max_ccn": 1,
         "max_nesting": 0, "duplication_pct": 100.0},
    ]}
    assert H.render_health(data) == ""


def test_non_source_files_are_excluded_entirely() -> None:
    """repowise scores markdown, YAML and baton's own .ai/ — none are code."""
    data = {"kpis": {}, "metrics": [
        {"file_path": "README.md", "score": 1.0, "max_ccn": 1, "max_nesting": 0},
        {"file_path": "pubspec.yaml", "score": 1.0, "max_ccn": 1, "max_nesting": 0},
        {"file_path": ".ai/config.yaml", "score": 1.0, "max_ccn": 1, "max_nesting": 0},
        {"file_path": "build/gen.dart", "score": 1.0, "max_ccn": 30, "max_nesting": 9},
    ]}
    assert H.render_health(data) == "", "nothing here is a refactoring target"


def test_source_files_survive_the_filter() -> None:
    data = {"kpis": {}, "metrics": [
        {"file_path": "lib/a.dart", "score": 3.0, "max_ccn": 20, "max_nesting": 2},
        {"file_path": "src/b.py", "score": 4.0, "max_ccn": 5, "max_nesting": 1},
        {"file_path": "web/c.ts", "score": 2.0, "max_ccn": 9, "max_nesting": 2},
    ]}
    out = H.render_health(data)
    for path in ("lib/a.dart", "src/b.py", "web/c.ts"):
        assert path in out
    assert "3 source files analyzed" in out


# ── ADR-028: computed once per project, cached in .ai/health.json ────────────

def _project(tmp_path):
    (tmp_path / ".ai").mkdir()
    (tmp_path / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    return tmp_path


def test_cache_is_written_then_reused_without_rerunning_repowise(tmp_path, monkeypatch):
    project = _project(tmp_path)
    calls = []
    monkeypatch.setattr(H, "_run_health", lambda p: calls.append(p) or SAMPLE)

    first = H.health_section(project)
    assert first and calls == [project]
    assert (project / H.CACHE_RELPATH).is_file(), "the analysis is persisted in .ai/"

    second = H.health_section(project)
    assert second == first
    assert calls == [project], "a fresh cache must not shell out again"


def test_refresh_forces_a_recompute(tmp_path, monkeypatch):
    project = _project(tmp_path)
    calls = []
    monkeypatch.setattr(H, "_run_health", lambda p: calls.append(p) or SAMPLE)
    H.health_section(project)
    H.health_section(project, refresh=True)
    assert len(calls) == 2


def test_cache_is_invalidated_by_a_source_edit(tmp_path, monkeypatch):
    """The point of the freshness rule: stale analysis is worse than none."""
    import os
    import time

    project = _project(tmp_path)
    calls = []
    monkeypatch.setattr(H, "_run_health", lambda p: calls.append(p) or SAMPLE)
    H.health_section(project)

    future = time.time() + 10
    os.utime(project / "a.py", (future, future))  # a source file changed after it
    H.health_section(project)
    assert len(calls) == 2, "an edited source file must invalidate the cache"


def test_cache_from_another_format_is_discarded_not_migrated(tmp_path, monkeypatch):
    project = _project(tmp_path)
    (project / H.CACHE_RELPATH).write_text('{"something": "else"}', encoding="utf-8")
    monkeypatch.setattr(H, "_run_health", lambda p: SAMPLE)
    assert H.read_cache(project) is None
    assert H.health_section(project), "it recomputes rather than failing"


def test_an_unwritable_cache_never_breaks_a_run(tmp_path, monkeypatch):
    project = _project(tmp_path)
    monkeypatch.setattr(H, "_run_health", lambda p: SAMPLE)
    monkeypatch.setattr(
        H.Path, "write_text", lambda *a, **k: (_ for _ in ()).throw(OSError("read-only"))
    )
    assert H.health_section(project), "the slice is still returned"


def test_cache_age_is_available_for_display(tmp_path, monkeypatch):
    project = _project(tmp_path)
    monkeypatch.setattr(H, "_run_health", lambda p: SAMPLE)
    assert H.cache_age_s(project) is None
    H.health_section(project)
    age = H.cache_age_s(project)
    assert age is not None and age < 5
