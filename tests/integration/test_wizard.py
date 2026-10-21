"""ADR-026: the interactive front door — bare `batonai` with no arguments.

The wizard itself is exercised end to end against the fake provider; the
non-TTY guarantee (scripts and CI must be unaffected) is tested separately,
because that is the promise ADR-026 makes to every existing user.
"""

import subprocess
from pathlib import Path

from typer.testing import CliRunner

from ai_orchestrator.cli import scan as scan_mod
from ai_orchestrator.cli import wizard
from ai_orchestrator.cli.app import app

FAKE_CLI = Path(__file__).parent / "fake_provider" / "fake_ai.py"
runner = CliRunner()

# The fake provider only edits the workspace when the request carries this
# directive; without it a run in a clean repo fails the ADR-007 no-change check.
REQ = "add a feature [[write@coder:feature.py:done]]"  # scoped: only the coder edits


FAKE_CONFIG = (
    "pipeline:\n  stages: [planner, coder]\n"
    "roles:\n  planner: {provider: fake}\n  coder: {provider: fake}\n"
    "providers:\n"
    f"  fake: {{command: {FAKE_CLI}, timeout_s: 30}}\n"
)


def wizard_project(tmp_path: Path, monkeypatch, *, init_ai: bool = True) -> Path:
    project = tmp_path / "proj"
    project.mkdir(parents=True)
    if init_ai:
        (project / ".ai").mkdir()
        (project / ".ai" / "config.yaml").write_text(FAKE_CONFIG)
    else:
        # No project config → the wizard would resolve the built-in defaults,
        # which name the REAL claude/codex binaries. On a developer machine those
        # exist and the health check passes by accident; on CI they do not and
        # the wizard blocks before asking anything (found when CI went red,
        # 2026-10-21). A user-level config keeps the test on the fake provider
        # while the project itself still has no .ai/ — exactly the scenario.
        user_cfg = tmp_path / "xdg" / "batonai" / "config.yaml"
        user_cfg.parent.mkdir(parents=True)
        user_cfg.write_text(FAKE_CONFIG)
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    (project / "main.py").write_text("x = 1\n")
    (project / "pyproject.toml").write_text("[project]\nname='p'\n")
    subprocess.run(["git", "add", "-A"], cwd=project, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "seed"],
        cwd=project, check=True,
    )
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.chdir(project)
    # Pin the health layer off: whether repowise is installed is a property of
    # the developer's machine, and it would otherwise flip `health=` in the
    # handoff. Its own behaviour is covered by tests/unit/test_scan.py.
    monkeypatch.setattr(scan_mod, "health_section", lambda _: "")
    return project


def force_tty(monkeypatch, interactive: bool) -> None:
    monkeypatch.setattr(wizard, "is_interactive", lambda: interactive)


def stub_run(monkeypatch) -> list[dict]:
    """Record the handoff instead of executing it.

    Required for any test whose project gets a *real* `ai init` config: that
    config names the real providers (claude/codex), and on a developer machine
    where those are installed, preflight passes and the wizard starts a real,
    token-spending pipeline. Tests must never be able to do that.
    """
    calls: list[dict] = []
    monkeypatch.setattr(wizard, "run", lambda **kw: calls.append(kw))
    return calls


# ── the non-TTY guarantee ───────────────────────────────────────────────────

def test_no_args_without_a_tty_prints_help_and_never_prompts(tmp_path, monkeypatch):
    """Piped/CI use must behave exactly as before ADR-026 — no hang, exit 0."""
    wizard_project(tmp_path, monkeypatch)
    force_tty(monkeypatch, False)
    result = runner.invoke(app, [], input="")  # no input available at all
    assert result.exit_code == 0
    assert "Usage:" in result.output
    assert "What do you want done" not in result.output


def test_subcommands_are_untouched_by_the_wizard(tmp_path, monkeypatch):
    """The callback must not intercept an explicit command."""
    wizard_project(tmp_path, monkeypatch)
    force_tty(monkeypatch, True)  # even with a "tty", an explicit command wins
    called: list[str] = []
    monkeypatch.setattr(wizard, "launch", lambda: called.append("launched"))
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert called == [], "explicit commands must never open the wizard"
    assert "batonai 0." in result.output


# ── the wizard proper ───────────────────────────────────────────────────────

def test_ready_project_shows_scan_and_runs_the_chosen_request(
    tmp_path, monkeypatch, fake_registry
):
    """Initialized project, no history yet → scan report, then straight to a run."""
    project = wizard_project(tmp_path, monkeypatch)
    force_tty(monkeypatch, True)

    result = runner.invoke(app, [], input=f"{REQ}\n")

    assert result.exit_code == 0, result.output
    assert "providers" in result.output and "all healthy" in result.output
    assert "What do you want done" in result.output
    assert (project / ".ai" / "runs").is_dir(), "the wizard handed off to a real run"


def test_uninitialized_project_offers_setup_before_asking(
    tmp_path, monkeypatch, fake_registry
):
    """No .ai/ → 'set up baton here?' comes first, and accepting creates it."""
    project = wizard_project(tmp_path, monkeypatch, init_ai=False)
    force_tty(monkeypatch, True)
    calls = stub_run(monkeypatch)  # `ai init` writes a real-provider config

    result = runner.invoke(app, [], input=f"y\n{REQ}\n")

    assert "Set up baton in this folder?" in result.output
    assert calls == [dict(
        request=REQ, with_designer=False, with_tester=False,
        with_publisher=False, fix_loop=False, health=False,
    )], "the request reaches `run` unchanged"
    assert (project / ".ai" / "config.yaml").is_file()
    assert (project / ".ai" / "project.md").is_file()
    setup_at = result.output.index("Set up baton")
    request_at = result.output.index("What do you want done")
    assert setup_at < request_at


def test_declining_setup_still_reaches_the_request(tmp_path, monkeypatch, fake_registry):
    project = wizard_project(tmp_path, monkeypatch, init_ai=False)
    force_tty(monkeypatch, True)
    stub_run(monkeypatch)

    result = runner.invoke(app, [], input=f"n\n{REQ}\n")

    assert not (project / ".ai" / "config.yaml").exists(), "declining must create nothing"
    assert "What do you want done" in result.output


def test_blocked_when_a_needed_provider_is_missing(tmp_path, monkeypatch, fake_registry):
    """A down provider exits 2 before any question is asked."""
    project = wizard_project(tmp_path, monkeypatch)
    (project / ".ai" / "config.yaml").write_text(
        "pipeline:\n  stages: [planner]\n"
        "roles:\n  planner: {provider: fake}\n"
        "providers:\n  fake: {command: /nonexistent-binary, timeout_s: 5}\n"
    )
    force_tty(monkeypatch, True)

    result = runner.invoke(app, [], input=f"{REQ}\n")

    assert result.exit_code == 2
    assert "What do you want done" not in result.output, "must not ask before blocking"


def test_history_shows_the_menu_and_quit_does_nothing(tmp_path, monkeypatch, fake_registry):
    """With a past run the wizard offers the menu; '5' (Quit) exits cleanly."""
    wizard_project(tmp_path, monkeypatch)
    force_tty(monkeypatch, True)

    first = runner.invoke(app, [], input=f"{REQ}\n")
    assert first.exit_code == 0, first.output

    second = runner.invoke(app, [], input="5\n")
    assert second.exit_code == 0, second.output
    assert "What next?" in second.output
    assert "Revise the last run" in second.output
    assert "last run" in second.output


def test_ctrl_c_at_a_prompt_cancels_cleanly(tmp_path, monkeypatch, fake_registry):
    """ADR-026: cancellation is exit 130 and creates nothing — not a stage failure."""
    project = wizard_project(tmp_path, monkeypatch, init_ai=False)
    force_tty(monkeypatch, True)
    stub_run(monkeypatch)

    result = runner.invoke(app, [], input="")  # EOF straight at the setup offer

    assert result.exit_code == 130
    assert "cancelled" in result.output
    assert not (project / ".ai" / "config.yaml").exists()


# ── the paths a coverage run showed were never executed ─────────────────────

def test_git_init_actually_creates_a_repo(tmp_path):
    """`_git_init` had no coverage at all — every other test starts in a repo."""
    project = tmp_path / "fresh"
    project.mkdir()
    assert wizard._git_init(project) is True
    assert (project / ".git").is_dir()


def test_git_init_reports_failure_without_raising(tmp_path, monkeypatch):
    def boom(*a, **kw):
        raise FileNotFoundError("git not installed")
    monkeypatch.setattr(wizard.subprocess, "run", boom)
    assert wizard._git_init(tmp_path) is False


def test_wizard_offers_git_init_in_a_non_repo(tmp_path, monkeypatch, fake_registry):
    """The GIT_INIT step of launch(), which no earlier test reached."""
    project = tmp_path / "nogit"
    (project / ".ai").mkdir(parents=True)
    (project / ".ai" / "config.yaml").write_text(
        "pipeline:\n  stages: [planner]\nroles:\n  planner: {provider: fake}\n"
        f"providers:\n  fake: {{command: {FAKE_CLI}, timeout_s: 30}}\n"
    )
    (project / "main.py").write_text("x = 1\n")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.chdir(project)
    monkeypatch.setattr(scan_mod, "health_section", lambda _: "")
    force_tty(monkeypatch, True)
    stub_run(monkeypatch)

    result = runner.invoke(app, [], input=f"y\n{REQ}\n")

    assert "Initialize a git repository here?" in result.output
    assert (project / ".git").is_dir(), "accepting the offer must really run git init"


def test_ask_request_reprompts_on_an_empty_answer(tmp_path, monkeypatch, fake_registry):
    wizard_project(tmp_path, monkeypatch)
    force_tty(monkeypatch, True)
    calls = stub_run(monkeypatch)

    result = runner.invoke(app, [], input="\n   \nfinally a request\n")

    assert calls and calls[0]["request"] == "finally a request"
    assert "enter a request" in result.output


def test_menu_falls_back_to_run_on_junk_input(tmp_path, monkeypatch, fake_registry):
    wizard_project(tmp_path, monkeypatch)
    force_tty(monkeypatch, True)
    first = runner.invoke(app, [], input=f"{REQ}\n")
    assert first.exit_code == 0, first.output

    calls = stub_run(monkeypatch)
    runner.invoke(app, [], input="banana\nthe fallback request\n")

    assert calls and calls[0]["request"] == "the fallback request"


def test_menu_dispatches_review_for_real(tmp_path, monkeypatch, fake_registry):
    """Executes the real `review` through the wizard.

    The point is the call convention: these are Typer commands whose defaults
    are `OptionInfo` objects, so a mis-shaped call fails here and nowhere else.
    """
    project = wizard_project(tmp_path, monkeypatch)
    (project / ".ai" / "config.yaml").write_text(
        "pipeline:\n  stages: [planner, coder, reviewer]\n"
        "roles:\n  planner: {provider: fake}\n  coder: {provider: fake}\n"
        "  reviewer: {provider: fake}\n"
        f"providers:\n  fake: {{command: {FAKE_CLI}, timeout_s: 30}}\n"
    )
    (project / "main.py").write_text("x = 2  # changed\n")  # something to review
    force_tty(monkeypatch, True)
    first = runner.invoke(app, [], input=f"{REQ}\n")
    assert first.exit_code == 0, first.output

    result = runner.invoke(app, [], input="3\n")  # 3 = Review my current changes

    assert result.exit_code == 0, result.output
    assert "OptionInfo" not in result.output


def test_menu_dispatches_publish_preview_and_commits_nothing(
    tmp_path, monkeypatch, fake_registry
):
    project = wizard_project(tmp_path, monkeypatch)
    force_tty(monkeypatch, True)
    first = runner.invoke(app, [], input=f"{REQ}\n")
    assert first.exit_code == 0, first.output
    before = subprocess.run(
        ["git", "rev-list", "--count", "HEAD"], cwd=project,
        capture_output=True, text=True,
    ).stdout.strip()

    result = runner.invoke(app, [], input="4\n")  # 4 = Publish

    after = subprocess.run(
        ["git", "rev-list", "--count", "HEAD"], cwd=project,
        capture_output=True, text=True,
    ).stdout.strip()
    assert before == after, "the wizard's publish is preview-only — it must not commit"
    assert "OptionInfo" not in result.output


def test_menu_dispatches_revise_for_real(tmp_path, monkeypatch, fake_registry):
    project = wizard_project(tmp_path, monkeypatch)
    force_tty(monkeypatch, True)
    first = runner.invoke(app, [], input=f"{REQ}\n")
    assert first.exit_code == 0, first.output
    runs_before = sorted((project / ".ai" / "runs").iterdir())

    result = runner.invoke(app, [], input="2\nmake it different\n")  # 2 = Revise

    assert "What should change?" in result.output
    assert "OptionInfo" not in result.output
    runs_after = sorted((project / ".ai" / "runs").iterdir())
    assert runs_after == runs_before, "revise continues the last run, never starts a new one"


def test_menu_out_of_range_number_falls_back_to_run(tmp_path, monkeypatch, fake_registry):
    wizard_project(tmp_path, monkeypatch)
    force_tty(monkeypatch, True)
    first = runner.invoke(app, [], input=f"{REQ}\n")
    assert first.exit_code == 0, first.output

    calls = stub_run(monkeypatch)
    runner.invoke(app, [], input="99\nout of range request\n")

    assert calls and calls[0]["request"] == "out of range request"


def test_broken_config_exits_2_before_scanning(tmp_path, monkeypatch):
    project = wizard_project(tmp_path, monkeypatch)
    (project / ".ai" / "config.yaml").write_text("pipeline: [this is not a mapping\n")
    force_tty(monkeypatch, True)

    result = runner.invoke(app, [], input=f"{REQ}\n")

    assert result.exit_code == 2
    assert "scanning" not in result.output


def test_is_interactive_reflects_the_real_streams(monkeypatch):
    """The one function every other test stubs — verify it isn't inverted."""
    class Stream:
        def __init__(self, tty): self._tty = tty
        def isatty(self): return self._tty

    monkeypatch.setattr(wizard.sys, "stdin", Stream(True))
    monkeypatch.setattr(wizard.sys, "stdout", Stream(True))
    assert wizard.is_interactive() is True

    monkeypatch.setattr(wizard.sys, "stdout", Stream(False))
    assert wizard.is_interactive() is False, "a redirected stdout is not interactive"


def test_scan_names_the_no_baseline_state_and_the_fix(tmp_path, monkeypatch, fake_registry):
    """ADR-029: distinct from 'uncommitted changes', and it prints the command.

    Live case: the wizard's own `git init` offer produced this state, and the
    generic dirty-tree warning told the user nothing useful.
    """
    project = tmp_path / "fresh"
    (project / ".ai").mkdir(parents=True)
    (project / ".ai" / "config.yaml").write_text(
        "pipeline:\n  stages: [planner]\nroles:\n  planner: {provider: fake}\n"
        f"providers:\n  fake: {{command: {FAKE_CLI}, timeout_s: 30}}\n"
    )
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)  # no commit
    (project / "main.py").write_text("x = 1\n")
    (project / "pyproject.toml").write_text("[project]\nname='p'\n")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.chdir(project)
    monkeypatch.setattr(scan_mod, "health_section", lambda _: "")
    force_tty(monkeypatch, True)
    stub_run(monkeypatch)

    result = runner.invoke(app, [], input="a request\n")

    assert "no commits yet" in result.output
    assert "git commit" in result.output, "the remedy is printed for the user to run"
    assert subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"], cwd=project, capture_output=True
    ).returncode != 0, "baton must never create the commit itself (ADR-020/029)"
