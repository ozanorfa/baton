"""Commit-message cleanup helpers for `batonai publish` (ADR-020)."""

from ai_orchestrator.cli.commands.publish import _commit_section, _strip_preamble


def test_strip_preamble_removes_chatty_lead_before_conventional_commit() -> None:
    text = (
        "Let me check the current changes in the working tree.\n"
        "feat: add CLI calculator for addition and subtraction"
    )
    assert _strip_preamble(text) == "feat: add CLI calculator for addition and subtraction"


def test_strip_preamble_keeps_a_clean_message_intact() -> None:
    text = "fix(parser): handle empty input\n\nDetail line."
    assert _strip_preamble(text) == text


def test_strip_preamble_handles_multiline_preamble() -> None:
    text = "Sure, here's a message.\nI'll summarize the diff.\nchore: bump deps\n\nbody"
    assert _strip_preamble(text) == "chore: bump deps\n\nbody"


def test_strip_preamble_leaves_non_conventional_text_unchanged() -> None:
    text = "Update the thing\nwith more detail"  # no conventional prefix → don't mangle
    assert _strip_preamble(text) == text


def test_strip_preamble_matches_scope_and_bang() -> None:
    assert _strip_preamble("preamble\nfeat(api)!: drop v1").startswith("feat(api)!: drop v1")


def test_commit_section_drops_pr_description_block() -> None:
    text = "feat: x\n\nbody\n\n## PR description\n\nlong pr body here"
    assert _commit_section(text) == "feat: x\n\nbody"


def test_commit_section_without_pr_block_is_unchanged() -> None:
    text = "feat: x\n\nbody"
    assert _commit_section(text) == text
