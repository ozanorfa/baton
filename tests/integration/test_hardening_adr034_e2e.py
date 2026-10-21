"""ADR-034 hardening pass — end-to-end pins on the fake provider.

* revise/fix-loop: a Coder pass that changes nothing is caught even though the
  tree is already dirty from the previous pass.
* untracked files with spaces reach the captured diff.
* Ctrl-C mid-stage: summary + exit 130, never "Aborted!" or "nothing changed".
* publish: a run's drafted message is reused only while the tree still matches.
"""

import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ai_orchestrator.cli.app import app
from ai_orchestrator.cli.commands import run as run_cmd
from ai_orchestrator.core.workspace import snapshot_changes
from ai_orchestrator.transport.headless import HeadlessTransport

FAKE_CLI = Path(__file__).parent / "fake_provider" / "fake_ai.py"
runner = CliRunner()
APPROVE = "[[output@reviewer:**Verdict** — APPROVE]]"


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
        cwd=cwd, capture_output=True, text=True, check=True,
    ).stdout


@pytest.fixture()
def project(tmp_path: Path, monkeypatch) -> Path:
    proj = tmp_path / "proj"
    (proj / ".ai").mkdir(parents=True)
    (proj / ".ai" / "config.yaml").write_text(
        "pipeline:\n  stages: [planner, coder, reviewer]\n"
        "roles:\n"
        "  planner: {provider: fake}\n"
        "  coder: {provider: fake}\n"
        "  reviewer: {provider: fake}\n"
        # publisher pinned to the zero-LLM floor: `batonai publish` falls back to
        # it, and the default (opencode) is a REAL client on a developer machine.
        "  publisher: {provider: deterministic}\n"
        "providers:\n"
        f"  fake: {{command: {FAKE_CLI}, timeout_s: 30}}\n"
    )
    _git(proj, "init", "-q")
    _git(proj, "add", "-A")
    _git(proj, "commit", "-qm", "init")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.chdir(proj)
    return proj


def only_run_id(project: Path) -> str:
    return next((project / ".ai" / "runs").iterdir()).name


# ── no-change detection survives a dirty tree ───────────────────────────────


def test_revise_with_a_do_nothing_coder_fails_instead_of_passing(project, fake_registry):
    first = runner.invoke(app, ["run", f"build [[write@coder:app.py:x=1]] {APPROVE}"],
                          env={"COLUMNS": "220"})
    assert first.exit_code == 0, first.output
    assert (project / "app.py").read_text() == "x=1\n"  # tree is now dirty

    # The revised coder replies happily but writes nothing. Before ADR-034 the
    # HEAD-relative check saw app.py and called this a success.
    revised = runner.invoke(app, ["revise", f"please tweak it {APPROVE}"], env={"COLUMNS": "220"})
    assert revised.exit_code == 1, revised.output
    assert "no workspace changes" in revised.output
    assert (project / "app.py").read_text() == "x=1\n"  # the user's prior work is untouched


def test_revise_that_really_edits_still_passes(project, fake_registry):
    first = runner.invoke(app, ["run", f"build [[write@coder:app.py:x=1]] {APPROVE}"],
                          env={"COLUMNS": "220"})
    assert first.exit_code == 0, first.output
    revised = runner.invoke(app, ["revise", f"set two [[write@coder:app.py:x=2]] {APPROVE}"],
                            env={"COLUMNS": "220"})
    assert revised.exit_code == 0, revised.output
    # the reviewer still sees the cumulative working-tree diff
    run_id = only_run_id(project)
    patch = (project / ".ai" / "runs" / run_id / "artifacts" / "diff.patch").read_text()
    assert "x=2" in patch


def test_declared_no_op_marker_still_honoured_on_revise(project, fake_registry):
    first = runner.invoke(app, ["run", f"build [[write@coder:app.py:x=1]] {APPROVE}"],
                          env={"COLUMNS": "220"})
    assert first.exit_code == 0, first.output
    revised = runner.invoke(
        app,
        ["revise", f"nothing [[output@coder:CHANGE_STATUS: no_changes_needed]] {APPROVE}"],
        env={"COLUMNS": "220"},
    )
    assert revised.exit_code == 0, revised.output


# ── untracked paths with spaces ─────────────────────────────────────────────


def test_untracked_file_with_a_space_reaches_the_diff(tmp_path: Path):
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "a.txt").write_text("one\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "c")
    (repo / "my new file.txt").write_text("spaced content\n")
    (repo / "ünïcödé.txt").write_text("unicode content\n")
    snap = snapshot_changes(repo)
    assert snap is not None and snap.changed
    assert "spaced content" in snap.patch
    assert "unicode content" in snap.patch


# ── Ctrl-C mid-stage ────────────────────────────────────────────────────────


class InterruptingTransport(HeadlessTransport):
    """Health checks (empty stdin) pass; the first real stage gets a Ctrl-C."""

    def run(self, invocation, on_line=None):
        if invocation.stdin:
            raise KeyboardInterrupt
        return super().run(invocation, on_line)


def test_ctrl_c_during_a_stage_exits_130_with_the_summary(project, fake_registry, monkeypatch):
    monkeypatch.setattr(run_cmd, "HeadlessTransport", InterruptingTransport)
    result = runner.invoke(app, ["run", "anything"], env={"COLUMNS": "220"})
    assert result.exit_code == 130, result.output
    assert "interrupted" in result.output
    assert "Aborted" not in result.output
    assert "nothing was changed" not in result.output
    run_id = only_run_id(project)
    assert f"batonai resume {run_id}" in result.output


# ── publish: stale run drafts are not reused ────────────────────────────────


def _seed_run_with_draft(project: Path, draft: str, diff_patch: str) -> None:
    run_dir = project / ".ai" / "runs" / "2026-01-01_0000_aaaa"
    (run_dir / "artifacts").mkdir(parents=True)
    (run_dir / "run.json").write_text(json.dumps({
        "run_id": "2026-01-01_0000_aaaa", "request": "r", "project_dir": str(project),
        "status": "succeeded", "stages": [],
    }))
    (run_dir / "artifacts" / "commit_message.md").write_text(draft)
    (run_dir / "artifacts" / "diff.patch").write_text(diff_patch)


def test_publish_reuses_run_draft_only_while_tree_matches(project, fake_registry):
    (project / "change.txt").write_text("new\n")
    current = snapshot_changes(project).patch
    _seed_run_with_draft(project, "feat: from the run\n", current)

    same = runner.invoke(app, ["publish"], env={"COLUMNS": "220"})
    assert same.exit_code == 0, same.output
    assert "feat: from the run" in same.output and "run 2026-01-01_0000_aaaa" in same.output

    (project / "change.txt").write_text("new and more\n")  # the user edited further
    stale = runner.invoke(app, ["publish"], env={"COLUMNS": "220"})
    assert stale.exit_code == 0, stale.output
    assert "feat: from the run" not in stale.output
    assert "different diff" in stale.output
    assert "source: deterministic" in stale.output  # fell through to the floor
