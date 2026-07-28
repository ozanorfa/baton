"""ADR-030: live progress notes from the provider's own event stream.

Two properties matter more than the feature itself and are pinned here: a note
can never fail a stage, and vendor output rendered to a terminal is untrusted.
"""

import json
import sys
from pathlib import Path

from ai_orchestrator.providers.base import _sanitize
from ai_orchestrator.providers.codex import CodexAdapter
from ai_orchestrator.transport.base import Invocation
from ai_orchestrator.transport.headless import HeadlessTransport


def _inv(script: str, timeout_s: int = 30) -> Invocation:
    return Invocation(
        argv=[sys.executable, "-c", script], stdin="", workdir=Path.cwd(), timeout_s=timeout_s
    )


# ── the transport ───────────────────────────────────────────────────────────

def test_without_a_sink_the_original_buffered_path_is_used():
    """The opt-in guarantee: no sink, no behaviour change."""
    result = HeadlessTransport().run(_inv("print('hello')"))
    assert result.ok and result.stdout.strip() == "hello"


def test_streaming_delivers_lines_while_collecting_the_same_stdout():
    seen: list[str] = []
    result = HeadlessTransport().run(
        _inv("for i in range(3): print('line', i, flush=True)"), on_line=seen.append
    )
    assert result.ok
    assert [s.strip() for s in seen] == ["line 0", "line 1", "line 2"]
    assert result.stdout.count("line") == 3, "stdout is still captured in full"


def test_streaming_captures_stderr_and_exit_code():
    result = HeadlessTransport().run(
        _inv("import sys; sys.stderr.write('boom'); sys.exit(3)"), on_line=lambda _l: None
    )
    assert result.exit_code == 3 and "boom" in result.stderr and not result.ok


def test_a_large_prompt_does_not_deadlock_the_child():
    """stdin is written from a thread precisely so this cannot hang."""
    big = "x" * 500_000
    inv = Invocation(
        argv=[sys.executable, "-c", "import sys; d=sys.stdin.read(); print(len(d))"],
        stdin=big, workdir=Path.cwd(), timeout_s=30,
    )
    result = HeadlessTransport().run(inv, on_line=lambda _l: None)
    assert result.ok and result.stdout.strip() == str(len(big))


def test_a_raising_sink_never_fails_the_stage():
    """A progress note is a convenience; the run is the product."""
    def boom(_line: str) -> None:
        raise RuntimeError("renderer exploded")

    result = HeadlessTransport().run(_inv("print('still fine')"), on_line=boom)
    assert result.ok and "still fine" in result.stdout


def test_streaming_times_out_and_reports_it():
    result = HeadlessTransport().run(
        _inv("import time\nprint('a', flush=True)\ntime.sleep(30)", timeout_s=2),
        on_line=lambda _l: None,
    )
    assert result.timed_out and not result.ok and "timed out" in (result.error or "")


def test_streaming_reports_a_missing_binary():
    inv = Invocation(argv=["/nonexistent-xyz"], stdin="", workdir=Path.cwd(), timeout_s=5)
    result = HeadlessTransport().run(inv, on_line=lambda _l: None)
    assert not result.ok and "binary not found" in (result.error or "")


# ── the codex adapter's notes (shapes captured from a real run) ─────────────

def _codex() -> CodexAdapter:
    return CodexAdapter(command="codex", model=None)


def test_codex_turns_a_shell_item_into_a_note():
    line = json.dumps({"type": "item.started", "item": {"command": "sed -n '1,20p' a.py"}})
    assert _codex().progress_note(line) == "$ sed -n '1,20p' a.py"


def test_codex_turns_a_text_item_into_a_note():
    line = json.dumps({"type": "item.started", "item": {"text": "I'll inspect the docs"}})
    assert _codex().progress_note(line) == "I'll inspect the docs"


def test_codex_emits_one_note_per_item_not_two():
    """`item.completed` repeats the same content — noting both doubles every line."""
    payload = {"item": {"command": "ls"}}
    assert _codex().progress_note(json.dumps({"type": "item.completed", **payload})) is None


def test_codex_ignores_noise_and_malformed_lines():
    for line in ("", "not json at all", "{broken", json.dumps({"type": "turn.started"})):
        assert _codex().progress_note(line) is None


def test_a_provider_that_streams_nothing_keeps_the_spinner():
    """The base class default — no other layer learns about it."""
    from ai_orchestrator.providers.base import ProviderAdapter

    assert ProviderAdapter.progress_note(_codex(), "anything") is None


# ── untrusted text ──────────────────────────────────────────────────────────

def test_notes_cannot_move_the_cursor_or_clear_the_screen():
    assert "\x1b" not in (_sanitize("\x1b[2J\x1b[H wiped", 90) or "")


def test_notes_cannot_smuggle_rich_markup():
    """Rendered through Rich, `[red]` would be interpreted as a style."""
    out = _sanitize("[red]danger[/red]", 90)
    assert out is not None and "[" not in out and "]" not in out


def test_notes_are_truncated_to_one_short_line():
    out = _sanitize("x" * 500, 90)
    assert out is not None and len(out) <= 90 and out.endswith("…")


def test_newlines_are_flattened_so_a_note_stays_one_line():
    out = _sanitize("first\nsecond\r\nthird", 90)
    assert out == "first second third"


def test_sanitize_returns_none_when_nothing_readable_remains():
    assert _sanitize("\x00\x01\x02", 90) is None


def test_codex_note_is_sanitized_end_to_end():
    line = json.dumps({"type": "item.started", "item": {"text": "\x1b[2J[red]evil[/red]"}})
    note = _codex().progress_note(line)
    assert note is not None and "\x1b" not in note and "[" not in note
