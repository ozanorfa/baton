"""Unit tests for the wizard's scan/decide split (cli/scan.py, ADR-026).

`decide()` is pure, so ADR-026's scan→action table is tested directly, row by
row — that table is the whole argument for why the wizard doesn't need an
R7/ADR-004 exemption, so it earns exhaustive coverage.

The IO helpers are tested for their guarantees only: a needed-provider check
narrower than `doctor`'s, and a front door that survives a broken run dir.
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from ai_orchestrator.cli import scan as S
from ai_orchestrator.cli.scan import LastRun, ProviderIssue, Step, WorkspaceScan
from ai_orchestrator.config.loader import load_config
from ai_orchestrator.context.awareness import WorkspaceMode
from ai_orchestrator.core.models import RunStatus


def make_scan(**overrides) -> WorkspaceScan:
    base = dict(
        project_dir=Path("/tmp/x"),
        is_empty=False,
        is_git=True,
        git_dirty=False,
        has_commits=True,
        mode=WorkspaceMode.ESTABLISHED,
        stack=("Python (pyproject.toml)",),
        has_ai_dir=True,
        last_run=None,
        health="",
        issues=(),
    )
    base.update(overrides)
    return WorkspaceScan(**base)


A_RUN = LastRun(
    run_id="20260728-120000",
    request="add dark mode",
    status=RunStatus.SUCCEEDED,
    verdict="APPROVE",
    created_at=datetime(2026, 7, 28, 12, 0, tzinfo=UTC),
)


# ── ADR-026's decision table, row by row ────────────────────────────────────

def test_unhealthy_provider_blocks_everything_else():
    """A down provider short-circuits: no setup offers, no request, exit 2."""
    state = make_scan(
        is_git=False, has_ai_dir=False,  # would otherwise produce setup steps
        issues=(ProviderIssue("codex", ("planner",), "binary not found"),),
    )
    assert S.decide(state) == (Step.BLOCK,)


def test_empty_dir_asks_for_the_request_before_setup():
    """Greenfield: 'what do you want to build' precedes 'shall I set up'."""
    steps = S.decide(make_scan(is_empty=True, is_git=False, has_ai_dir=False,
                               mode=WorkspaceMode.GREENFIELD))
    assert steps == (Step.ASK_REQUEST, Step.GIT_INIT, Step.BATON_INIT, Step.RUN)
    assert steps.index(Step.ASK_REQUEST) < steps.index(Step.BATON_INIT)


def test_established_uninitialized_offers_setup_then_asks():
    steps = S.decide(make_scan(has_ai_dir=False))
    assert steps == (Step.BATON_INIT, Step.ASK_REQUEST, Step.RUN)


def test_non_git_offers_git_init_first():
    steps = S.decide(make_scan(is_git=False, has_ai_dir=False))
    assert steps == (Step.GIT_INIT, Step.BATON_INIT, Step.ASK_REQUEST, Step.RUN)


def test_ready_project_with_history_gets_the_menu():
    assert S.decide(make_scan(last_run=A_RUN)) == (Step.MENU,)


def test_initialized_but_no_runs_yet_asks_instead_of_showing_a_menu():
    """A menu whose only live entry is 'new request' is worse than the question."""
    assert S.decide(make_scan(last_run=None)) == (Step.ASK_REQUEST, Step.RUN)


def test_run_is_always_preceded_by_a_request():
    """The wizard asserts this; make it a property of the table, not luck."""
    for state in (
        make_scan(is_empty=True, is_git=False, has_ai_dir=False),
        make_scan(has_ai_dir=False),
        make_scan(last_run=None),
        make_scan(is_git=False),
    ):
        steps = S.decide(state)
        if Step.RUN in steps:
            assert steps.index(Step.ASK_REQUEST) < steps.index(Step.RUN)


def test_decide_is_pure_and_stable():
    state = make_scan(last_run=A_RUN)
    assert S.decide(state) == S.decide(state)


# ── needed_providers: narrower than doctor, on purpose ──────────────────────

def test_needed_providers_ignores_disabled_roles(tmp_path):
    """The default Publisher is disabled, so a missing opencode must not block."""
    config = load_config(tmp_path).config
    needed = S.needed_providers(config)
    assert "opencode" not in needed, "a disabled role's provider is not needed"
    assert "claude" in needed and "coder" in needed["claude"]


def test_needed_providers_maps_every_enabled_stage(tmp_path):
    config = load_config(tmp_path).config
    needed = S.needed_providers(config)
    covered = {stage for stages in needed.values() for stage in stages}
    expected = {
        s for s in config.pipeline.stages
        if s in config.roles and config.roles[s].enabled
    }
    assert covered == expected


# ── IO helpers: guarantees only ─────────────────────────────────────────────

def test_is_empty_dir_ignores_tooling_noise(tmp_path):
    assert S.is_empty_dir(tmp_path)
    (tmp_path / ".git").mkdir()
    (tmp_path / ".ai").mkdir()
    assert S.is_empty_dir(tmp_path), "a folder with only tooling dirs is still empty"
    (tmp_path / "main.py").write_text("x = 1")
    assert not S.is_empty_dir(tmp_path)


def test_git_state_on_a_non_repo(tmp_path):
    assert S.git_state(tmp_path) == (False, False, False)


def test_last_run_is_none_without_history(tmp_path):
    assert S.last_run(tmp_path) is None


def test_last_run_survives_a_corrupt_run_dir(tmp_path):
    """A half-written run must degrade to 'no history', never crash the wizard."""
    run_dir = tmp_path / ".ai" / "runs" / "20260728-000000"
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text("{ this is not json")
    assert S.last_run(tmp_path) is None


@pytest.mark.parametrize("mode", [WorkspaceMode.GREENFIELD, WorkspaceMode.ESTABLISHED])
def test_scan_skips_health_on_greenfield(tmp_path, monkeypatch, mode):
    """ADR-025 keeps health established-only; the wizard must not widen that."""
    called: list[Path] = []
    monkeypatch.setattr(S, "detect_mode", lambda _: mode)
    monkeypatch.setattr(S, "health_section", lambda p: called.append(p) or "hotspots")
    monkeypatch.setattr(S, "check_providers", lambda *_: ())
    state = S.scan(tmp_path, load_config(tmp_path).config, transport=None)
    assert bool(called) is (mode is WorkspaceMode.ESTABLISHED)
    assert state.health == ("hotspots" if mode is WorkspaceMode.ESTABLISHED else "")


def _single_stage(tmp_path, provider: str):
    """A config whose only enabled stage is the planner, bound to `provider`.

    Narrowing to one stage keeps the health check off every *other* provider,
    so no adapter is invoked and no transport is needed.
    """
    config = load_config(tmp_path).config
    config.pipeline.stages = ["planner"]
    config.roles["planner"].provider = provider
    return config


def test_check_providers_flags_a_role_bound_to_an_unknown_provider(tmp_path):
    config = _single_stage(tmp_path, "nosuchprovider")
    config.providers["nosuchprovider"] = config.providers["codex"].model_copy()
    issues = S.check_providers(config, transport=None)
    assert [(i.provider, i.roles) for i in issues] == [("nosuchprovider", ("planner",))]
    assert "unknown provider" in issues[0].detail


def test_check_providers_flags_a_provider_with_no_configuration(tmp_path):
    """A role pointing at a provider with no providers: entry at all."""
    issues = S.check_providers(_single_stage(tmp_path, "unconfigured"), transport=None)
    assert [(i.provider, i.detail) for i in issues] == [("unconfigured", "not configured")]


def test_git_state_survives_git_being_absent(tmp_path, monkeypatch):
    def boom(*a, **kw):
        raise FileNotFoundError("no git")
    monkeypatch.setattr(S.subprocess, "run", boom)
    assert S.git_state(tmp_path) == (False, False, False)


def test_is_empty_dir_on_an_unreadable_path(tmp_path):
    assert S.is_empty_dir(tmp_path / "does-not-exist") is False


# ── ADR-029: a repo with no baseline commit is its own state ────────────────

def test_git_state_reports_a_repo_without_commits(tmp_path):
    import subprocess
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "a.py").write_text("x = 1\n")
    is_git, dirty, has_commits = S.git_state(tmp_path)
    assert (is_git, has_commits) == (True, False), "a fresh repo has no baseline"

    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "seed"],
        cwd=tmp_path, check=True,
    )
    assert S.git_state(tmp_path) == (True, False, True)


def test_no_baseline_does_not_change_the_decision_table(tmp_path):
    """ADR-029 is reporting only — it must not add or reorder wizard steps."""
    assert S.decide(make_scan(has_commits=False)) == S.decide(make_scan(has_commits=True))
