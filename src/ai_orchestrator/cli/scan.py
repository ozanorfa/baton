"""Workspace scan for the interactive front door (ADR-026).

Split in two on purpose, mirroring `context/health.py`'s IO/pure split:

  * `scan()` performs the IO — filesystem, git, provider health, repowise.
  * `decide()` is **pure**: a fixed table from observed state to the steps the
    wizard offers. No model call, no judgment (ADR-004 and this file is the
    reason ADR-026 needs no R7 exemption) — same state in, same steps out,
    which is exactly what makes the table unit-testable.

`decide()` is also the layer a future REPL (ADR-026, deferred) would reuse, so
it deliberately knows nothing about prompting or rendering.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from ai_orchestrator.config.schema import AppConfig
from ai_orchestrator.context.awareness import (
    EXCLUDED_DIRS,
    WorkspaceMode,
    detect_mode,
    stack_labels,
)
from ai_orchestrator.context.health import health_section
from ai_orchestrator.core.models import Health, RunStatus
from ai_orchestrator.core.reporter import build_report
from ai_orchestrator.core.run_manager import RunManager
from ai_orchestrator.providers import load_all
from ai_orchestrator.providers.registry import UnknownProviderError
from ai_orchestrator.transport.base import Transport

GIT_STATUS_TIMEOUT_S = 10


@dataclass(frozen=True)
class LastRun:
    run_id: str
    request: str
    status: RunStatus
    verdict: str | None
    created_at: datetime


@dataclass(frozen=True)
class ProviderIssue:
    provider: str
    roles: tuple[str, ...]
    detail: str


@dataclass(frozen=True)
class WorkspaceScan:
    """Everything the wizard observed, before any decision is taken."""

    project_dir: Path
    is_empty: bool
    is_git: bool
    git_dirty: bool
    has_commits: bool  # a repo with no HEAD has no baseline to diff against (ADR-029)
    mode: WorkspaceMode
    stack: tuple[str, ...]
    has_ai_dir: bool
    last_run: LastRun | None
    health: str
    issues: tuple[ProviderIssue, ...]


class Step(StrEnum):
    """One row of ADR-026's scan→action table."""

    BLOCK = "block"  # a needed provider is down — exit 2 before anything else
    GIT_INIT = "git_init"
    BATON_INIT = "baton_init"
    ASK_REQUEST = "ask_request"
    RUN = "run"
    MENU = "menu"


def decide(state: WorkspaceScan) -> tuple[Step, ...]:
    """ADR-026's table, as pure code. The wizard executes what this returns."""
    if state.issues:
        return (Step.BLOCK,)

    setup: list[Step] = []
    if not state.is_git:
        setup.append(Step.GIT_INIT)
    if not state.has_ai_dir:
        setup.append(Step.BATON_INIT)

    if state.is_empty:
        # An empty folder has nothing to report on, so "set this up?" would be a
        # question about nothing. What they came to build is the only useful
        # first question; setup follows once there is a reason for it.
        return (Step.ASK_REQUEST, *setup, Step.RUN)

    if state.has_ai_dir and state.last_run is not None:
        return (*setup, Step.MENU)

    # Initialized but no history yet (or being initialized right now): a menu
    # whose only live entry is "new request" is worse than just asking.
    return (*setup, Step.ASK_REQUEST, Step.RUN)


def needed_providers(config: AppConfig) -> dict[str, list[str]]:
    """Providers bound to roles that will actually run: in the stage list AND enabled.

    Deliberately narrower than `ai doctor`, which reports every configured
    provider: the wizard must not block a run because `opencode` is missing
    when the Publisher stage is disabled (the default).
    """
    needed: dict[str, list[str]] = {}
    for stage in config.pipeline.stages:
        role = config.roles.get(stage)
        if role is None or not role.enabled:
            continue
        needed.setdefault(role.provider, []).append(stage)
    return needed


def check_providers(config: AppConfig, transport: Transport) -> tuple[ProviderIssue, ...]:
    """Health-check only the providers this project's pipeline actually needs."""
    registry = load_all()
    issues: list[ProviderIssue] = []
    for name, roles in needed_providers(config).items():
        provider_cfg = config.providers.get(name)
        if provider_cfg is None:
            issues.append(ProviderIssue(name, tuple(roles), "not configured"))
            continue
        try:
            adapter_cls = registry.get(name)
        except UnknownProviderError as exc:
            issues.append(ProviderIssue(name, tuple(roles), str(exc)))
            continue
        adapter = adapter_cls.configure(
            provider_cfg.command, provider_cfg.model, provider_cfg.allow_commands
        )
        health: Health = adapter.health_check(transport)
        if not health.ok:
            issues.append(ProviderIssue(name, tuple(roles), health.detail or "unhealthy"))
    return tuple(issues)


def is_empty_dir(project_dir: Path) -> bool:
    """True when nothing but tooling/VCS noise is present.

    A folder holding only `.git/` or `.ai/` still counts as empty — the user
    has not written anything yet, which is what the greenfield row is about.
    """
    try:
        for entry in project_dir.iterdir():
            if entry.name in EXCLUDED_DIRS or entry.name.startswith("."):
                continue
            return False
    except OSError:
        return False
    return True


def git_state(project_dir: Path) -> tuple[bool, bool, bool]:
    """(is a git repo, working tree is dirty, has at least one commit).

    ADR-029: "repo with no commits" is its own state, not a flavour of dirty.
    Without a HEAD every file reads as a change, so diff capture and ADR-007's
    no-change safety net both lose their baseline — observed live when the
    wizard's `git init` offer was accepted on a real project.
    """
    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=project_dir,
            capture_output=True,
            text=True, encoding="utf-8",
            timeout=GIT_STATUS_TIMEOUT_S,
            shell=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False, False, False
    if proc.returncode != 0:
        return False, False, False
    head = _git_ok(project_dir, "rev-parse", "--verify", "HEAD")
    return True, bool(proc.stdout.strip()), head


def _git_ok(project_dir: Path, *args: str) -> bool:
    try:
        proc = subprocess.run(
            ["git", *args], cwd=project_dir, capture_output=True,
            text=True, encoding="utf-8", timeout=GIT_STATUS_TIMEOUT_S, shell=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False
    return proc.returncode == 0


def last_run(project_dir: Path) -> LastRun | None:
    manager = RunManager(project_dir)
    run_id = manager.latest_run_id()
    if run_id is None:
        return None
    try:
        state = manager.load_run(run_id)
        report = build_report(state, manager)
    except (FileNotFoundError, OSError, ValueError):
        return None  # a half-written run must never break the front door
    return LastRun(
        run_id=run_id,
        request=state.request,
        status=state.status,
        verdict=report.verdict,
        created_at=state.created_at,
    )


def scan(project_dir: Path, config: AppConfig, transport: Transport) -> WorkspaceScan:
    """Observe the workspace. Does IO; takes no decisions (see `decide`)."""
    mode = detect_mode(project_dir)
    is_git, dirty, has_commits = git_state(project_dir)
    # ADR-025: health is established-only (greenfield has no history to score);
    # `health_section` already returns "" when repowise is absent or fails.
    health = health_section(project_dir) if mode is WorkspaceMode.ESTABLISHED else ""
    return WorkspaceScan(
        project_dir=project_dir,
        is_empty=is_empty_dir(project_dir),
        is_git=is_git,
        git_dirty=dirty,
        has_commits=has_commits,
        mode=mode,
        stack=tuple(stack_labels(project_dir)),
        has_ai_dir=(project_dir / ".ai" / "config.yaml").is_file(),
        last_run=last_run(project_dir),
        health=health,
        issues=check_providers(config, transport),
    )
