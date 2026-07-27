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
    assert "113 files analyzed" in out
    assert "average health 8.8/10" in out
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
    (idx / "wiki.db").write_text("x")
    H._cleanup_index(tmp_path, index_preexisted=False)
    assert not idx.exists()


def test_cleanup_preserves_users_own_index(tmp_path: Path) -> None:
    idx = tmp_path / H._INDEX_DIR
    idx.mkdir()
    (idx / "wiki.db").write_text("x")
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
