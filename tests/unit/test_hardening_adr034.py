"""ADR-034 hardening pass — the unit-level pins.

Each test here guards one finding of the 2026-10-21 full review. Integration
counterparts live in tests/integration/test_hardening_adr034.py.
"""

import json
import os
import sys
from pathlib import Path

import pytest

from ai_orchestrator.cli import render
from ai_orchestrator.cli.app import _known_commands, rewrite_argv
from ai_orchestrator.core.engine import PipelineEngine
from ai_orchestrator.core.models import (
    AgentRequest,
    AgentResult,
    Capabilities,
    Health,
    RunStatus,
    StageSpec,
    StageStatus,
    utcnow,
)
from ai_orchestrator.core.reporter import save_report
from ai_orchestrator.core.routing import ResolvedStage
from ai_orchestrator.core.run_manager import RunManager
from ai_orchestrator.core.workspace import parse_porcelain_z
from ai_orchestrator.observability.events import EventLog
from ai_orchestrator.providers.base import ProviderAdapter
from ai_orchestrator.providers.claude import FORBIDDEN_COMMANDS, ClaudeCodeAdapter
from ai_orchestrator.transport.base import Invocation, TransportResult
from ai_orchestrator.transport.headless import HeadlessTransport

# ── engine: an unexpected exception is recorded, never left as "running" ────


class OkAdapter(ProviderAdapter):
    name = "ok"
    capabilities = Capabilities()

    def __init__(self):
        super().__init__(command="ok-bin")

    def health_check(self, transport) -> Health:
        return Health(ok=True)

    def build_invocation(self, request) -> Invocation:
        return Invocation(argv=["ok-bin"], stdin=request.prompt, workdir=request.workdir,
                          timeout_s=request.timeout_s)

    def parse(self, raw: TransportResult) -> AgentResult:
        return AgentResult(success=True, text="fine")


class ExplodingTransport:
    """A transport bug: not a TransportResult, a crash."""

    def run(self, invocation, on_line=None):
        raise RuntimeError("pipe exploded")


def _stage(name: str, adapter) -> ResolvedStage:
    return ResolvedStage(
        spec=StageSpec(name=name, role=name, output=f"{name}.md"),
        provider_name="ok", adapter=adapter, timeout_s=10, enabled=True, allow_edits=False,
    )


def test_unexpected_exception_marks_run_failed_before_propagating(tmp_path: Path) -> None:
    manager = RunManager(tmp_path)
    engine = PipelineEngine(manager, ExplodingTransport())
    with pytest.raises(RuntimeError, match="pipe exploded"):
        engine.execute("req", [_stage("planner", OkAdapter())])

    run_id = manager.latest_run_id()
    state = manager.load_run(run_id)
    assert state.status is RunStatus.FAILED, "never left as RUNNING on disk"
    planner = state.stage("planner")
    assert planner.status is StageStatus.FAILED
    assert "RuntimeError: pipe exploded" in planner.error
    assert f"batonai resume {run_id}" in planner.error
    events = [e["event"] for e in EventLog(manager.logs_dir(run_id)).read()]
    assert events[-2:] == ["stage_failed", "run_finished"]


# ── render: an unfinished run must never read as a success ──────────────────


def test_summary_of_a_running_run_is_not_reported_as_success(tmp_path: Path, capsys) -> None:
    manager = RunManager(tmp_path)
    state = manager.create_run("demo", [
        StageSpec(name="planner", role="planner", output="plan.md"),
        StageSpec(name="coder", role="coder", output="changes.md"),
    ])
    state.stages[0].status = StageStatus.SUCCEEDED
    state.stages[1].status = StageStatus.RUNNING
    state.stages[1].started_at = utcnow()
    manager.save(state)  # a crash left it like this

    render.render_run_summary(state, manager.run_dir(state.run_id), None)
    out = capsys.readouterr().out
    assert "run succeeded" not in out
    assert "not finished" in out and "coder" in out
    assert f"batonai resume {state.run_id}" in out


def test_runs_list_labels_an_unfinished_run(tmp_path: Path, capsys) -> None:
    manager = RunManager(tmp_path)
    state = manager.create_run("demo", [StageSpec(name="planner", role="planner", output="p.md")])
    state.stages[0].status = StageStatus.RUNNING
    report = save_report(state, manager)
    render.render_runs_list([(state, report)])
    out = capsys.readouterr().out
    assert "unfinished" in out and "…" in out


# ── workspace: porcelain -z parsing ─────────────────────────────────────────


def test_status_entries_keep_paths_with_spaces_and_skip_rename_sources() -> None:
    raw = "?? my file.txt\0 M src/app.py\0R  new name.py\0old.py\0?? ünïcödé.md\0"
    assert parse_porcelain_z(raw) == [
        ("??", "my file.txt"),
        (" M", "src/app.py"),
        ("R ", "new name.py"),
        ("??", "ünïcödé.md"),
    ]


def test_status_entries_empty() -> None:
    assert parse_porcelain_z("") == []


# ── transport: undecodable bytes and orphaned grandchildren ────────────────


def _inv(script: str, timeout_s: int = 10) -> Invocation:
    return Invocation(argv=[sys.executable, "-c", script], stdin="", workdir=Path.cwd(),
                      timeout_s=timeout_s)


@pytest.mark.parametrize("streaming", [False, True])
def test_undecodable_output_degrades_instead_of_crashing(streaming: bool) -> None:
    script = "import sys; sys.stdout.buffer.write(b'ok \\xff\\xfe end\\n')"
    sink = (lambda _l: None) if streaming else None
    result = HeadlessTransport().run(_inv(script), on_line=sink)
    assert result.ok
    assert result.stdout.startswith("ok ") and result.stdout.rstrip().endswith("end")
    assert "�" in result.stdout  # replaced, not raised


def _alive(pid: int) -> bool:
    if sys.platform == "win32":
        import subprocess

        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True
        ).stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)  # signal 0 = existence check (POSIX only)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


@pytest.mark.parametrize("streaming", [False, True])
def test_timeout_kills_the_whole_process_tree(streaming: bool) -> None:
    """A provider CLI spawns helpers; after a timeout none of them may survive."""
    script = (
        "import subprocess, sys, time\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        "print(child.pid, flush=True)\n"
        "time.sleep(60)\n"
    )
    sink = (lambda _l: None) if streaming else None
    result = HeadlessTransport().run(_inv(script, timeout_s=1), on_line=sink)
    assert result.timed_out
    grandchild = int(result.stdout.strip().splitlines()[0])
    # SIGKILL is asynchronous; give the kernel a moment before asserting.
    import time
    deadline = time.monotonic() + 3
    while _alive(grandchild) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not _alive(grandchild), "grandchild outlived the timed-out stage"


# ── claude adapter ──────────────────────────────────────────────────────────


def _req(**kw) -> AgentRequest:
    defaults = dict(role="coder", prompt="do it", workdir=Path("/tmp/p"), timeout_s=900)
    return AgentRequest(**{**defaults, **kw})


def test_claude_non_object_json_is_a_failed_result_not_a_crash() -> None:
    adapter = ClaudeCodeAdapter(command="claude")
    for payload in ('["a", "b"]', '"just a string"', "42"):
        result = adapter.parse(TransportResult(exit_code=0, stdout=payload, stderr="",
                                               duration_s=0.1))
        assert not result.success and "JSON object" in (result.error or "")


def test_claude_allow_commands_grants_bash_but_blocks_git_history_and_remotes() -> None:
    adapter = ClaudeCodeAdapter.configure("claude", None, allow_commands=True)
    inv = adapter.build_invocation(_req(allow_edits=True))
    assert inv.argv[inv.argv.index("--allowedTools") + 1] == "Bash"
    blocked = inv.argv[inv.argv.index("--disallowedTools") + 1].split(",")
    assert set(blocked) == set(FORBIDDEN_COMMANDS)
    for must in ("Bash(git commit:*)", "Bash(git push:*)", "Bash(gh:*)", "Bash(git reset:*)"):
        assert must in blocked


def test_claude_allow_commands_is_off_by_default_and_never_for_readonly_roles() -> None:
    default = ClaudeCodeAdapter.configure("claude", None)
    assert "--allowedTools" not in default.build_invocation(_req(allow_edits=True)).argv
    granted = ClaudeCodeAdapter.configure("claude", None, allow_commands=True)
    assert "--allowedTools" not in granted.build_invocation(
        _req(role="planner", allow_edits=False)
    ).argv


def test_configure_keeps_plugin_constructors_untouched() -> None:
    """Third-party adapters (ADR-009) with their own __init__ still construct."""

    class Plugin(ProviderAdapter):
        name = "plug"
        capabilities = Capabilities()

        def __init__(self, command: str, model: str | None = None):
            super().__init__(command, model)
            self.extra = "kept"

        def health_check(self, transport):
            return Health(ok=True)

        def build_invocation(self, request):
            raise NotImplementedError

        def parse(self, raw):
            raise NotImplementedError

    adapter = Plugin.configure("bin", "m", allow_commands=True)
    assert (adapter.extra, adapter.model, adapter.allow_commands) == ("kept", "m", True)


# ── reporter: verdict is case-insensitive, normalised ───────────────────────


def test_verdict_is_matched_case_insensitively_and_normalised(tmp_path: Path) -> None:
    manager = RunManager(tmp_path)
    state = manager.create_run(
        "r", [StageSpec(name="reviewer", role="reviewer", output="review.md")]
    )
    manager.save_artifact(state, "review.md", "## verdict\n\nneeds work — see findings\n")
    assert save_report(state, manager).verdict == "NEEDS WORK"
    manager.save_artifact(state, "review.md", "Verdict: Approve With Notes\n")
    assert save_report(state, manager).verdict == "APPROVE WITH NOTES"
    data = json.loads((manager.run_dir(state.run_id) / "report.json").read_text(encoding="utf-8"))
    assert data["verdict"] == "APPROVE WITH NOTES"


# ── app: the command set is derived, not hand-maintained ────────────────────


def test_known_commands_cover_every_registered_command() -> None:
    names = _known_commands()
    for expected in ("run", "ask", "doctor", "config", "init", "runs", "resume", "revise",
                     "review", "publish", "health", "setup"):
        assert expected in names
    assert rewrite_argv(["batonai", "setup"]) == ["batonai", "setup"]
    assert rewrite_argv(["batonai", "do the thing"]) == ["batonai", "run", "do the thing"]


# ── config: unknown-key paths name the mapping entry they sit under ──────────


def test_unknown_key_path_includes_the_role_name() -> None:
    import warnings

    from ai_orchestrator.config.schema import AppConfig, warn_unknown_keys

    config = AppConfig.model_validate({
        "pipeline": {"stages": ["coder"]},
        "roles": {"coder": {"provider": "claude", "bogus_key": 1}},
        "providers": {"claude": {"command": "claude"}},
    })
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        assert warn_unknown_keys(config, "x.yaml") == ["roles.coder.bogus_key"]


def test_deterministic_header_is_singular_for_one_file() -> None:
    from ai_orchestrator.providers.deterministic import message_from_status

    assert message_from_status("?? new file.py\0").startswith("chore: update 1 file\n")
    assert message_from_status(" M a.py\0 M b.py\0").startswith("chore: update 2 files\n")
