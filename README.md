# batonai

*User guide: [English](docs/HOW_TO_USE.md) · [Türkçe](docs/HOW_TO_USE.tr.md)*

A **local-first CLI** that turns multiple AI coding assistants (Claude Code, Codex CLI, Antigravity CLI) into one deterministic development pipeline:

```bash
batonai "Add Face ID support to the Flutter application"
```

…runs **Planner** (Codex) → **Designer** (Antigravity, optional) → **Coder** (Claude Code) → **Tester** (zero-LLM, optional) → **Reviewer** (Codex) → **Publisher** (opencode, optional), forwards each stage's output to the next automatically, preserves every artifact on disk, and prints an execution report with real token counts.

**Not another agent framework:** routing is plain Python from YAML config — no supervisor LLM, no dynamic delegation, zero tokens spent on coordination.

## Status

**v0.1.0 — first public release** (2026-10-21; PyPI publication pending, install from GitHub meanwhile — see below). Everything described in this README is built, tested and in use:

- the six-stage pipeline with Claude Code, Codex, Antigravity, opencode, a zero-LLM test runner and a zero-LLM commit-message floor;
- resumable runs, `revise`/`review`/`publish`, same-provider session chaining, the interactive front door, per-project provider/model setup, live progress notes, optional code-health context;
- a 2026-10-21 hardening pass (ADR-034) that closed every *silent* failure path a from-scratch review found.

**Verified on:** macOS; one real Flutter app end to end (Face ID feature, verdict APPROVE WITH NOTES), plus a 348-test suite that needs no AI access. **Not yet:** Linux (expected to work), Windows (not supported), any measurement of output quality against a single-model session — see [CHANGELOG.md](CHANGELOG.md) for releases, [docs/WORKLOG.md](docs/WORKLOG.md) for history, [docs/DECISIONS.md](docs/DECISIONS.md) for the reasoning behind every design choice.

**What's next** (ordered, not scheduled): a live tmux view of provider processes · more roles (documentation, security) · policy-driven retries · an MCP server interface · per-project memory. Details in [docs/IMPLEMENTATION_PLAN.md §4](docs/IMPLEMENTATION_PLAN.md).

## Prerequisites

- macOS (tested) or Linux (expected to work, unverified), Python ≥3.12, and [uv](https://docs.astral.sh/uv/) or [pipx](https://pipx.pypa.io/)
- **Required** provider CLIs, installed and logged in: `claude` (Claude Code — the Coder) and `codex` (Codex CLI — Planner and Reviewer)
- **Optional**, only for stages that are off by default: `agy` (Antigravity CLI — the Designer, `--with-designer`), `opencode` (free client — the Publisher, `--with-publisher`), `repowise` (code-health hotspots, `--health`). `batonai doctor` lists these as *optional* and does not fail on them.

## Install & quickstart

```bash
uv tool install batonai        # or: pipx install batonai

cd any-project                 # ideally a git repo with a clean tree
batonai                        # ← that's it: scans, sets up, asks what you want
```

Latest `main` instead of the last release: `uv tool install git+https://github.com/ozanorfa/baton`.
Working on baton itself: `git clone https://github.com/ozanorfa/baton && cd baton && uv tool install --editable .`
Upgrade: `uv tool upgrade batonai` · Remove: `uv tool uninstall batonai`.

Bare **`batonai`** opens the interactive front door (ADR-026): it checks your providers, detects the stack, reports code-health hotspots, offers the one-time `init` if the project isn't set up, and then asks what you want done. Nothing to memorize.

Prefer typing the whole thing? Every step is still an ordinary command:

```bash
batonai doctor                 # verify all providers are healthy
batonai init                   # once per project; auto-detects the stack
batonai "do something useful"  # run the pipeline
```

## Everyday commands

| Command | What it does |
|---|---|
| `batonai` | **Start here.** Interactive: scan the project, offer the missing setup, ask what you want, run it (ADR-026). Piped/CI use prints help instead, unchanged |
| `batonai "<request>"` | Run the full pipeline (`--with-designer` UI stage · `--with-tester` runs your tests, zero-LLM · `--with-publisher` drafts a commit message · `--fix-loop` auto-fixes once on NEEDS WORK · `--health` injects repowise code-health hotspots, ADR-025) |
| `batonai revise "<correction>"` | Iterate on the **last** run without starting over — the Coder resumes its own session and applies the correction, then the Reviewer re-checks (ADR-019) |
| `batonai review` | Send the current working-tree diff to the Reviewer — check your own changes with a different model, no pipeline, read-only (ADR-022) |
| `batonai publish` | Preview a drafted commit message; `--commit`/`--push` commit (and push) — the only command that runs git, and only when you ask (ADR-020) |
| `batonai resume <run-id>` | Continue a failed run from the failed stage — completed stages are never re-paid |
| `batonai runs list` / `batonai runs show <id>` | Run history: status, per-stage glyphs, cost, verdict |
| `batonai ask --role coder "<q>"` | One cheap single-role call, no pipeline |
| `batonai setup` | Change which AI handles each role and which model it runs — revisable any time; the defaults stay the defaults (ADR-032) |
| `batonai health` | Print the repowise code-health hotspots every stage is told about — zero tokens, no run needed |
| `batonai doctor` / `batonai config show` / `batonai init` | Provider health (optional providers marked, never block) · effective config with sources · project setup |

Exit codes: `0` success · `1` a stage failed · `2` config/usage error · `130` you cancelled the wizard.

**What the cost figure means:** the `$` value shown after a run is the provider-reported **API-equivalent** value — if you use subscription plans (Claude Pro/Max, ChatGPT), you are **not charged per run**; the run consumes your plan's included quota instead (that's what session limits are). Only API-key users pay it as a real bill. A typical pipeline run "costs" $0.50–1.50 of quota, dominated by fixed per-stage overhead — so it barely grows with task size.

**Quota control:** for small tasks use `batonai ask` (one call, no pipeline); set `providers: {claude: {model: haiku}}` in `.ai/config.yaml` for lighter runs; trim stages per project: `pipeline: {stages: [planner, coder]}`.

**Letting the Coder verify its work:** headless Claude Code denies shell commands by default, so the Coder cannot run your tests unless you opt in: `providers: {claude: {allow_commands: true}}`. This grants Bash **except** git history/remote operations and `gh`, which stay blocked by an explicit deny list (ADR-034) — the "no stage ever commits" guarantee is unaffected.

More: [docs/MANUAL_TESTING.md](docs/MANUAL_TESTING.md) — every command you can try, with token-cost notes.

## ⚠ Trust model

The Coder stage **edits your repository unattended** (scoped to the project directory). Safety net: run from a clean git tree (warned otherwise), every change is diffable, the Reviewer reports on the actual diff, and no pipeline stage ever commits. Details: [docs/MVP.md](docs/MVP.md) §7, [docs/DECISIONS.md](docs/DECISIONS.md) ADR-007.

**No pipeline stage ever runs `git commit`, `git push`, or any GitHub/remote operation — for any role, in any mode.** This cannot be silently escalated by config or a flag. The optional Publisher stage (`--with-publisher`, off by default) only *drafts* a commit message and PR description as a text file (ADR-014). The **one** command that runs git is `batonai publish --commit`/`--push` — a separate, **user-invoked** step (never a role) that shows exactly what it will commit and asks you to confirm first (ADR-020). Nothing reaches your history unless you explicitly ask for it, each time.

## Documentation

| Doc | What's in it |
|---|---|
| [HOW_TO_USE.md](docs/HOW_TO_USE.md) (English) · [HOW_TO_USE.tr.md](docs/HOW_TO_USE.tr.md) (Türkçe) | **Start here** — plain-language user guide |
| [CHANGELOG.md](CHANGELOG.md) | What changed in each release |
| [IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) | Vision, goals, the M0–M5 milestones (complete) and the post-MVP roadmap |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Layers, adapter contract, context system, verified CLI behavior |
| [DECISIONS.md](docs/DECISIONS.md) | 34 ADRs — why everything is the way it is |
| [PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md) | Repo layout + runtime footprint |
| [TASKS.md](docs/TASKS.md) | The original 35-task build plan, all done — kept as history |
| [MVP.md](docs/MVP.md) | The first full version, stage by stage — kept as history |
| [MANUAL_TESTING.md](docs/MANUAL_TESTING.md) | Hands-on test commands per milestone |
| [WORKLOG.md](docs/WORKLOG.md) | Session-by-session history |
| [IDEAS.md](docs/IDEAS.md) | Evaluated ideas and what became of them — most have since shipped (ADR-017/018/025); the MCP-based context reducer is still parked |

## Development

Contributions go through pull requests against a protected `main` — see [CONTRIBUTING.md](CONTRIBUTING.md).

```bash
uv sync
uv run pytest          # unit + contract (recorded real CLI fixtures) + integration (fake provider)
uv run ruff check .
```

**Releasing** (maintainers): bump `version` in `pyproject.toml`, add the section to `CHANGELOG.md`, commit, then `git tag v<version> && git push origin v<version>`. The `release` workflow verifies the tag matches the version, runs the suite, builds, publishes to PyPI via trusted publishing and creates the GitHub release.

If you move or rename the checkout, the old `.venv` keeps absolute paths to the previous location (`uv run pytest` then fails to import `ai_orchestrator`): `rm -rf .venv && uv sync`, and `unset VIRTUAL_ENV` if your shell still exports the old one.
