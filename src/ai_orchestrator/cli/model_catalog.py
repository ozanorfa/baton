"""Model suggestions for `batonai init`/`batonai setup` (ADR-031/032).

Single source, shared by both commands — they previously carried separate
copies of the same lookup tables, which is how `codex` ended up with no
suggestion or hint in either place (found live, 2026-07-29): the dict simply
had no entry for it.

Never validated. Model identifiers are vendor-specific and change often, so an
unrecognised answer is always passed through to the CLI, which is the
authority — this module only decides what to show *before* the user types.
"""

from __future__ import annotations

import subprocess

from ai_orchestrator.transport.headless import resolve_executable

DISCOVERY_TIMEOUT_S = 5
# A prompt suggestion list, not a picker — stop well short of a full dump.
DISCOVERY_MAX = 8

# Providers whose own CLI can list its current models. Verified live (agy
# 2026-07-29): `agy models` prints one model per line, no auth/network needed
# beyond what's already configured, and returns instantly. Neither `claude`
# nor `codex` expose an equivalent — there is nothing to shell out to for them.
_DISCOVERY_ARGS: dict[str, tuple[str, ...]] = {
    "antigravity": ("models",),
}

# Static fallbacks and hints, used when live discovery isn't available (or
# fails). These are the well-known, slow-changing *aliases* the CLI itself
# documents (`claude --help`), not a snapshot of model ids that will rot.
STATIC_SUGGESTIONS: dict[str, tuple[str, ...]] = {
    "claude": ("opus", "sonnet", "haiku"),
}
STATIC_HINTS: dict[str, str] = {
    "claude": "opus = strongest/slowest · haiku = cheapest/fastest "
    "(aliases resolve to the latest model of that tier)",
    "codex": "no fixed list — check ~/.codex/config.toml's `model =` line, or "
    "your account's own model picker, for a valid id",
    "opencode": "no fixed list — this is whatever free-tier model you pointed "
    "opencode at via `opencode auth` (an OpenRouter :free id, a Google AI Studio "
    "key, or an opencode promo model)",
}


# `init` runs before any project config exists, so there is no configured
# `command` to read yet — these are the same defaults `defaults.yaml` ships.
DEFAULT_COMMANDS: dict[str, str] = {
    "claude": "claude",
    "codex": "codex",
    "antigravity": "agy",
    "opencode": "opencode",
}


def discover_models(provider: str, command: str) -> tuple[str, ...]:
    """Live model list from the provider's own CLI, when it offers one.

    Best-effort by construction: any failure (binary missing, timeout, non-zero
    exit, empty output) yields no suggestions, never an error — this is a
    convenience for the prompt, not a dependency of `init`/`setup`.
    """
    extra = _DISCOVERY_ARGS.get(provider)
    if extra is None:
        return ()
    try:
        proc = subprocess.run(
            [resolve_executable(command), *extra],  # `agy.cmd` on Windows (ADR-035)
            # stdin=DEVNULL, not inherited: live-tested (2026-07-29), `agy models`
            # returns its plain list in ~2s when stdin is /dev/null, but hangs
            # indefinitely when it inherits an ambient terminal/pipe stdin — this
            # command must never gamble on whatever fd the caller happens to have.
            stdin=subprocess.DEVNULL,
            capture_output=True, text=True, encoding="utf-8",
            timeout=DISCOVERY_TIMEOUT_S, shell=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return ()
    if proc.returncode != 0 or not proc.stdout.strip():
        return ()
    lines = tuple(line.strip() for line in proc.stdout.splitlines() if line.strip())
    return lines[:DISCOVERY_MAX]


def suggestions_for(provider: str, command: str) -> tuple[str, ...]:
    """Model suggestions to show for this provider — live first, then static."""
    live = discover_models(provider, command)
    return live if live else STATIC_SUGGESTIONS.get(provider, ())


def hint_for(provider: str) -> str | None:
    """A one-line note on how to choose (cost/speed trade-off, or where to look)."""
    return STATIC_HINTS.get(provider)
