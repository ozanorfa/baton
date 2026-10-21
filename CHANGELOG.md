# Changelog

All notable changes to `batonai` are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/). The *why* behind each change lives
in [docs/DECISIONS.md](docs/DECISIONS.md) (ADRs) and the session-by-session
history in [docs/WORKLOG.md](docs/WORKLOG.md).

## [Unreleased]

## [0.2.0] — 2026-10-21

### Added
- **Windows support** (ADR-035): portable process-tree control (`taskkill` on
  Windows, `killpg` on POSIX), npm `.cmd` shims found via `PATHEXT`, untracked
  file diffs generated in Python instead of via `/dev/null`, explicit UTF-8 for
  every file and subprocess, `%APPDATA%\batonai\config.yaml` for the user
  config, and the full test suite running on `windows-latest` in CI.

### Changed
- `batonai doctor` distinguishes **required** providers (bound to an enabled
  stage) from **optional** ones; optional providers that are missing are shown
  as `○ optional` and no longer fail the command (docs pass, 2026-10-21).
- `main` is protected: changes land by pull request with green CI on Ubuntu,
  macOS and Windows.

## [0.1.0] — 2026-10-21

First public release. Everything below was built between 2026-07-11 and
2026-10-21; see the ADR numbers for the reasoning.

### Added
- Deterministic pipeline over AI coding CLIs: Planner → Designer (optional) →
  Coder → Tester (optional, zero-LLM) → Reviewer → Publisher (optional),
  routed purely from YAML config — no supervisor model (ADR-004).
- Provider adapters for Claude Code, Codex CLI, Antigravity CLI, opencode, a
  zero-LLM `deterministic` commit-message floor and a zero-LLM `testrunner`
  (ADR-003, ADR-012, ADR-017, ADR-018, ADR-024). Third-party adapters plug in
  via the `ai_orchestrator.providers` entry-point group (ADR-009).
- Every run persisted under `.ai/runs/<run-id>/` with prompts, artifacts, raw
  logs and a JSONL event stream; `batonai resume` continues a failed run from
  the failed stage (ADR-005).
- `batonai revise` continues the last run with a correction, the Coder
  resuming its own session (ADR-019); `batonai review` sends the working-tree
  diff to the Reviewer (ADR-022); `batonai publish --commit/--push` is the one
  user-invoked git step (ADR-020). No pipeline stage ever runs git (ADR-014).
- Same-provider session chaining (ADR-015), per-stage context contracts and a
  four-layer prompt system (ADR-006, ADR-013), opt-in repowise code-health
  hotspots (ADR-025, ADR-028), live progress notes from the provider's own
  event stream (ADR-030).
- Interactive front door: bare `batonai` scans the workspace, offers the
  missing setup and asks what you want (ADR-026). `batonai init` and
  `batonai setup` choose providers and models per project (ADR-031, ADR-032).
- Hardening pass (ADR-034): no silent states — crashes recorded instead of
  leaving a run "running", change detection against a pre-stage baseline,
  provider process trees killed on timeout/Ctrl-C, untracked files with
  spaces captured, stale commit drafts not reused, and an opt-in
  `allow_commands` so the Coder can run tests with git history/remotes
  mechanically blocked.

### Notes
- macOS is the tested platform; Linux is expected to work but is unverified.
- Requires the provider CLIs (`claude`, `codex`, optionally `agy`,
  `opencode`) to be installed and authenticated separately.

[Unreleased]: https://github.com/ozanorfa/baton/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/ozanorfa/baton/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/ozanorfa/baton/releases/tag/v0.1.0
