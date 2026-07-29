"""Shared model suggestions for `init`/`setup` (ADR-031/032).

Regression coverage for the live bug (2026-07-29): codex had no entry in
either command's local dict, so a user who didn't already know a valid model
id saw a bare `codex:` prompt with nothing to go on.
"""

import subprocess

from ai_orchestrator.cli import model_catalog as C


def test_every_default_provider_has_something_to_show() -> None:
    """The regression itself: no provider should offer neither hint nor suggestion."""
    for provider in C.DEFAULT_COMMANDS:
        has_hint = C.hint_for(provider) is not None
        has_suggestions = bool(C.STATIC_SUGGESTIONS.get(provider)) or provider in C._DISCOVERY_ARGS
        assert has_hint or has_suggestions, f"{provider} offers the user nothing to go on"


def test_codex_gets_a_hint_even_with_no_fixed_suggestion_list() -> None:
    assert C.suggestions_for("codex", "codex") == ()
    assert C.hint_for("codex") is not None and "no fixed list" in C.hint_for("codex")


def test_claude_keeps_its_curated_aliases() -> None:
    assert C.suggestions_for("claude", "claude") == ("opus", "sonnet", "haiku")


def test_discovery_is_attempted_only_for_providers_that_support_it(monkeypatch):
    calls = []
    def _fail(*a, **k):
        calls.append(a)
        raise AssertionError("should not be called")
    monkeypatch.setattr(C.subprocess, "run", _fail)
    assert C.discover_models("codex", "codex") == ()
    assert C.discover_models("claude", "claude") == ()
    assert calls == [], "no CLI call should be attempted for providers with no discovery command"


def test_antigravity_discovery_parses_a_real_shaped_output(monkeypatch):
    fake = subprocess.CompletedProcess(
        args=[], returncode=0,
        stdout="Gemini 3.6 Flash (High)\nGemini 3.6 Flash (Medium)\nClaude Sonnet 4.6 (Thinking)\n",
        stderr="",
    )
    monkeypatch.setattr(C.subprocess, "run", lambda *a, **k: fake)
    models = C.discover_models("antigravity", "agy")
    assert models == (
        "Gemini 3.6 Flash (High)", "Gemini 3.6 Flash (Medium)", "Claude Sonnet 4.6 (Thinking)",
    )


def test_antigravity_discovery_fails_safe(monkeypatch):
    """Missing binary, timeout, or a bad exit — all yield no suggestions, never an error."""
    def boom(*a, **k):
        raise FileNotFoundError("no agy")
    monkeypatch.setattr(C.subprocess, "run", boom)
    assert C.discover_models("antigravity", "agy") == ()

    monkeypatch.setattr(
        C.subprocess, "run",
        lambda *a, **k: subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="x"),
    )
    assert C.discover_models("antigravity", "agy") == ()


def test_discovery_is_bounded_not_a_dump(monkeypatch):
    huge = "\n".join(f"model-{i}" for i in range(50))
    fake = subprocess.CompletedProcess(args=[], returncode=0, stdout=huge, stderr="")
    monkeypatch.setattr(C.subprocess, "run", lambda *a, **k: fake)
    assert len(C.discover_models("antigravity", "agy")) == C.DISCOVERY_MAX


def test_live_discovery_is_preferred_over_the_static_list(monkeypatch):
    fake = subprocess.CompletedProcess(args=[], returncode=0, stdout="Live Model X\n", stderr="")
    monkeypatch.setattr(C.subprocess, "run", lambda *a, **k: fake)
    assert C.suggestions_for("antigravity", "agy") == ("Live Model X",)


def test_falls_back_to_static_when_discovery_yields_nothing(monkeypatch):
    monkeypatch.setattr(
        C.subprocess, "run",
        lambda *a, **k: subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr=""),
    )
    # antigravity has no STATIC_SUGGESTIONS entry, so the fallback is legitimately empty
    assert C.suggestions_for("antigravity", "agy") == ()


def test_discovery_never_inherits_ambient_stdin(monkeypatch):
    """Live-found bug (2026-07-29): `agy models` hangs when it inherits the
    caller's stdin, but returns in ~2s when stdin is /dev/null. discover_models
    must never gamble on whatever fd the parent process happens to have."""
    captured = {}

    def fake_run(*args, **kwargs):
        captured.update(kwargs)
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="m\n", stderr="")

    monkeypatch.setattr(C.subprocess, "run", fake_run)
    C.discover_models("antigravity", "agy")
    assert captured.get("stdin") is subprocess.DEVNULL
