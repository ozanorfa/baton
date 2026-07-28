"""Workspace change detection for edit-stages (T26, ADR-007).

Captured reality (see providers/claude.py docstring): a permission-blocked
headless run reports success at the protocol level. The only reliable
detector is the workspace itself — after an edit-stage, either files changed
or something is wrong. This module answers "did anything change, and what?"
via git, without ever mutating the user's index.
"""

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WorkspaceSnapshot:
    changed: bool
    patch: str  # unified diff incl. untracked files ("" when unchanged)


def _git(project_dir: Path, *args: str) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=project_dir, capture_output=True, text=True, timeout=30, shell=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


# The orchestrator's own footprint must never count as "the coder changed
# something" — .ai/ holds run state written by this very pipeline.
#
# Generated artifacts are excluded for the same reason: nobody authored them,
# so attributing them to the coder wastes reviewer attention and can flip a
# verdict. Git already hides *ignored* files, so this only matters where a
# project's .gitignore is incomplete — which is exactly when it bites (a live
# `batonai review` returned NEEDS WORK over stray `.pyc` files, 2026-07-28).
#
# Deliberately conservative: only names that are never hand-written source in
# any language. `build/`, `dist/` and `target/` are NOT here — they are real
# source directories in some projects, and when they are build output they are
# already gitignored.
_GENERATED = (
    "__pycache__", "*.pyc", "*.pyo", ".pytest_cache", ".ruff_cache",
    ".mypy_cache", "node_modules", ".DS_Store",
)
_EXCLUDE = (
    ":(exclude).ai",
    ":(exclude).ai/**",
    *(f":(exclude,glob)**/{name}" for name in _GENERATED),
    *(f":(exclude,glob){name}" for name in _GENERATED),
    *(f":(exclude,glob)**/{name}/**" for name in _GENERATED),
)


def snapshot_changes(project_dir: Path) -> WorkspaceSnapshot | None:
    """None = git unavailable or not a repo (detection impossible, caller skips)."""
    status = _git(project_dir, "status", "--porcelain", "-uall", "--", ".", *_EXCLUDE)
    if status is None or status.returncode != 0:
        return None
    lines = [line for line in status.stdout.splitlines() if line.strip()]
    if not lines:
        return WorkspaceSnapshot(changed=False, patch="")

    parts: list[str] = []
    tracked = _git(project_dir, "diff", "HEAD", "--", ".", *_EXCLUDE)
    if tracked is None or tracked.returncode != 0:
        tracked = _git(project_dir, "diff", "--", ".", *_EXCLUDE)  # repo without HEAD yet
    if tracked is not None and tracked.stdout:
        parts.append(tracked.stdout)

    for line in lines:
        if line.startswith("??"):
            rel = line[3:].strip()
            untracked = _git(project_dir, "diff", "--no-index", "--", "/dev/null", rel)
            if untracked is not None and untracked.stdout:
                parts.append(untracked.stdout)

    return WorkspaceSnapshot(changed=True, patch="".join(parts))
