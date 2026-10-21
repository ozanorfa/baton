"""`batonai publish [--commit|--push]` — draft a commit message, then (only on an
explicit user command) git commit and push (ADR-020).

This is the ONE deliberate, user-triggered exception to ADR-014's "no role runs
git": the drafting (LLM or the deterministic floor) and the git write are
separate steps, and no pipeline role ever touches git. Without --commit/--push
it only previews the draft. --commit commits (git add -A); --push commits + pushes.
"""

import re
import subprocess
from pathlib import Path

import typer

from ai_orchestrator.cli import render
from ai_orchestrator.config.loader import ConfigError, load_config
from ai_orchestrator.core.models import AgentRequest
from ai_orchestrator.core.run_manager import RunManager
from ai_orchestrator.core.workspace import snapshot_changes
from ai_orchestrator.providers import load_all
from ai_orchestrator.providers.base import invoke
from ai_orchestrator.providers.registry import UnknownProviderError
from ai_orchestrator.transport.headless import HeadlessTransport


def _git(project_dir: Path, *args: str, stdin: str = "") -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=project_dir, input=stdin,
        capture_output=True, text=True, errors="replace", timeout=30, shell=False,
    )


def _git_or_none(project_dir: Path, *args: str) -> subprocess.CompletedProcess | None:
    """`_git` for read-only probes: None when git is missing or hangs."""
    try:
        return _git(project_dir, *args)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None


def _changed_files(project_dir: Path) -> list[str] | None:
    """Porcelain status lines, or None if git is missing / this isn't a repo."""
    status = _git_or_none(project_dir, "status", "--porcelain")
    if status is None or status.returncode != 0:
        return None
    return [ln for ln in status.stdout.splitlines() if ln.strip()]


def _commit_section(text: str) -> str:
    """Keep only the commit message if the draft also embeds a PR-description section."""
    idx = text.lower().find("pr description")
    if idx == -1:
        return text.strip()
    line_start = text.rfind("\n", 0, idx)
    return text[: line_start if line_start != -1 else idx].strip()


_CC_SUBJECT = re.compile(
    r"^(feat|fix|docs|chore|refactor|test|style|perf|build|ci|revert)(\([^)]*\))?!?:\s", re.I
)


def _strip_preamble(text: str) -> str:
    """Drop conversational preamble a chatty free-tier model prepends before the
    real message (e.g. 'Let me check the working tree.' then the actual commit).
    Anchors on the first Conventional-Commits subject line; if none is found,
    returns the text unchanged — it never mangles a message it can't parse."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if _CC_SUBJECT.match(line.strip()):
            return "\n".join(lines[i:]).strip()
    return text.strip()


def _deterministic_draft(project_dir: Path) -> tuple[str | None, str]:
    from ai_orchestrator.providers.deterministic import DeterministicAdapter

    adapter = DeterministicAdapter(command="git")
    request = AgentRequest(
        role="publisher", prompt="", workdir=project_dir, timeout_s=60, allow_edits=False
    )
    result = invoke(adapter, HeadlessTransport(), request)
    return (result.text, "deterministic (git diff)") if result.success else (None, "")


def _fresh_draft(project_dir: Path) -> tuple[str | None, str]:
    """Draft via the publisher role's configured provider; fall back to the
    deterministic floor if it's unavailable or fails."""
    try:
        loaded = load_config(project_dir)
    except ConfigError:
        return _deterministic_draft(project_dir)
    role_cfg = loaded.config.roles.get("publisher")
    if role_cfg is None:
        return _deterministic_draft(project_dir)
    try:
        adapter_cls = load_all().get(role_cfg.provider)
    except UnknownProviderError:
        return _deterministic_draft(project_dir)

    provider_cfg = loaded.config.providers[role_cfg.provider]
    adapter = adapter_cls.configure(
        provider_cfg.command, provider_cfg.model, provider_cfg.allow_commands
    )
    snapshot = snapshot_changes(project_dir)  # tracked + untracked, baton's own files excluded
    diff = snapshot.patch if snapshot is not None else ""
    prompt = (
        "Write a concise Conventional Commits message for these working-tree changes. "
        "Output only the commit message, no preamble.\n\n" + (diff or "(no diff)")
    )
    request = AgentRequest(
        role="publisher", prompt=prompt, workdir=project_dir,
        timeout_s=provider_cfg.timeout_s, allow_edits=False,
    )
    result = invoke(adapter, HeadlessTransport(), request)
    if result.success and result.text.strip():
        return _strip_preamble(result.text), f"{role_cfg.provider} (drafted)"
    return _deterministic_draft(project_dir)


def _run_draft_is_current(manager: RunManager, state, project_dir: Path) -> bool:
    """A run's drafted message describes the diff *that run* produced. Reuse it
    only while the working tree still shows exactly that diff (ADR-034): once
    the user has edited further — or the draft belongs to an unrelated earlier
    run — it would describe changes that are not the ones being committed."""
    try:
        recorded = manager.load_artifact(state, "diff.patch")
    except (FileNotFoundError, OSError):
        return False
    current = snapshot_changes(project_dir)
    return current is not None and current.patch == recorded


def _resolve_draft(project_dir: Path) -> tuple[str | None, str]:
    """Precedence: the latest run's commit_message.md while it still matches the
    working tree; otherwise draft fresh."""
    manager = RunManager(project_dir)
    run_id = manager.latest_run_id()
    if run_id is not None:
        try:
            state = manager.load_run(run_id)
            text = manager.load_artifact(state, "commit_message.md")
        except (FileNotFoundError, OSError, ValueError):
            text = ""
        if text.strip():
            if _run_draft_is_current(manager, state, project_dir):
                return text, f"run {run_id}"
            render.console.print(
                f"[dim]the draft from run {run_id} describes a different diff than the "
                "working tree now holds — drafting afresh.[/dim]"
            )
    return _fresh_draft(project_dir)


def publish(
    message: str = typer.Option(None, "-m", "--message", help="Use this commit message verbatim."),
    commit: bool = typer.Option(False, "--commit", help="git add -A && git commit (no push)."),
    push: bool = typer.Option(False, "--push", help="git add -A && git commit && git push."),
    yes: bool = typer.Option(False, "--yes", help="Skip the confirmation prompt."),
) -> None:
    """Draft a commit message; with --commit/--push, commit (and push) on your command."""
    project_dir = Path.cwd()

    if message is not None:
        text, source = message, "--message"
    else:
        text, source = _resolve_draft(project_dir)
        if text is None:
            render.render_error('could not draft a commit message — pass -m "<msg>".')
            raise typer.Exit(code=1)

    render.render_commit_draft(text, source)

    if not (commit or push):
        return  # preview only — never touch git

    changed = _changed_files(project_dir)
    if changed is None:
        render.render_error("not a git repository (or git unavailable) — cannot commit.")
        raise typer.Exit(code=2)
    render.render_publish_plan(changed, will_push=push)
    if not changed:
        raise typer.Exit(code=0)

    if not yes and not typer.confirm("Proceed?"):
        render.console.print("aborted — nothing committed.")
        raise typer.Exit(code=0)

    add = _git(project_dir, "add", "-A")
    if add.returncode != 0:
        render.render_error(f"git add failed: {add.stderr.strip()}")
        raise typer.Exit(code=1)
    committed = _git(project_dir, "commit", "-F", "-", stdin=_commit_section(text))
    if committed.returncode != 0:
        render.render_error(
            f"git commit failed: {committed.stderr.strip() or committed.stdout.strip()}"
        )
        raise typer.Exit(code=1)
    render.console.print(f"[green]✓ committed[/green]\n[dim]{committed.stdout.strip()}[/dim]")

    if push:
        pushed = _git(project_dir, "push")
        if pushed.returncode != 0:
            render.render_error(
                "commit succeeded but push failed:\n"
                + (pushed.stderr.strip() or pushed.stdout.strip())
            )
            raise typer.Exit(code=1)
        render.console.print("[green]✓ pushed[/green]")
