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
            cwd=project_dir, capture_output=True, text=True, errors="replace",
            timeout=30, shell=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
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
EXCLUDE_PATHSPECS = (
    ":(exclude).ai",
    ":(exclude).ai/**",
    *(f":(exclude,glob)**/{name}" for name in _GENERATED),
    *(f":(exclude,glob){name}" for name in _GENERATED),
    *(f":(exclude,glob)**/{name}/**" for name in _GENERATED),
)


def parse_porcelain_z(porcelain_z: str) -> list[tuple[str, str]]:
    """Parse `git status --porcelain -z` into (XY, path) pairs.

    `-z` gives NUL-separated records with **unquoted** paths — the plain
    porcelain format quotes anything with a space or non-ASCII byte
    (`?? "my file.txt"`), which used to make such untracked files vanish from
    the captured diff (ADR-034). Renames/copies carry a second NUL-terminated
    field (the original path) that must be skipped.
    """
    entries: list[tuple[str, str]] = []
    tokens = porcelain_z.split("\0")
    i = 0
    while i < len(tokens):
        record = tokens[i]
        i += 1
        if len(record) < 3:
            continue
        xy, path = record[:2], record[3:]
        if xy[0] in "RC" or xy[1] in "RC":
            i += 1  # the rename/copy source path follows as its own record
        entries.append((xy, path))
    return entries


def snapshot_changes(project_dir: Path) -> WorkspaceSnapshot | None:
    """None = git unavailable or not a repo (detection impossible, caller skips)."""
    status = _git(
        project_dir, "status", "--porcelain", "-z", "-uall", "--", ".", *EXCLUDE_PATHSPECS
    )
    if status is None or status.returncode != 0:
        return None
    entries = parse_porcelain_z(status.stdout)
    if not entries:
        return WorkspaceSnapshot(changed=False, patch="")

    parts: list[str] = []
    tracked = _git(project_dir, "diff", "HEAD", "--", ".", *EXCLUDE_PATHSPECS)
    if tracked is None or tracked.returncode != 0:
        tracked = _git(project_dir, "diff", "--", ".", *EXCLUDE_PATHSPECS)  # repo without HEAD yet
    if tracked is not None and tracked.stdout:
        parts.append(tracked.stdout)

    for xy, rel in entries:
        if xy == "??":
            untracked = _git(project_dir, "diff", "--no-index", "--", "/dev/null", rel)
            if untracked is not None and untracked.stdout:
                parts.append(untracked.stdout)

    return WorkspaceSnapshot(changed=True, patch="".join(parts))
