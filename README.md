# AI Coding Orchestrator

A **local-first CLI** that turns multiple AI coding assistants (Claude Code, Codex CLI, Antigravity CLI) into one deterministic development pipeline:

```bash
ai "Add Face ID support to the Flutter application"
```

…runs **Planner** (Codex) → **Designer** (Antigravity, optional) → **Coder** (Claude Code) → **Tester** (zero-LLM, optional) → **Reviewer** (Codex) → **Publisher** (opencode, optional), forwards each stage's output to the next automatically, preserves every artifact on disk, and prints an execution report with real token counts.

**Not another agent framework:** routing is plain Python from YAML config — no supervisor LLM, no dynamic delegation, zero tokens spent on coordination.

## Status

**All planned milestones complete (M0–M5, 2026-07-12).** MVP acceptance passed on a real Flutter app (Face ID feature, reviewer verdict APPROVE WITH NOTES); hardening shipped (`ai resume`, `ai runs`, Ctrl-C safety), workspace awareness landed (ADR-013: established projects get a docs index + read-first instruction; greenfield get propose-structure guidance), an optional Publisher role (ADR-014: drafts a commit message + PR description on a provider of your choice, independent of the coder — never runs git itself), and same-provider session chaining (ADR-015: consecutive same-vendor stages resume each other's session instead of cold-starting — live-verified to cut redundant repo re-exploration without changing which model does which job). Since then: quota-spread defaults now put the shallow Publisher on a free client (ADR-017: opencode) with a zero-LLM commit-message floor (ADR-018: `deterministic`); and an interactive loop landed — `ai revise` iterates on the last run with the Coder resuming its own session (ADR-019), and `ai publish --commit/--push` is the one user-invoked git step (ADR-020). Next: the remaining post-MVP roadmap (tmux observability, new roles, MCP + repowise context reducer, memory). See [docs/TASKS.md](docs/TASKS.md) for progress and [docs/WORKLOG.md](docs/WORKLOG.md) for history.

## Prerequisites

- macOS, Python ≥3.12, [uv](https://docs.astral.sh/uv/)
- The provider CLIs, installed and authenticated: `claude` (Claude Code), `codex` (Codex CLI), `agy` (Antigravity CLI)
- Optional: `opencode` (free client — the default Publisher provider; point it at a free-tier model). Not needed unless you enable the Publisher stage.

## Install & quickstart

```bash
git clone <this-repo> && cd ai-agent-test
uv tool install --editable .      # installs the global `ai` command

ai doctor                          # verify all providers are healthy
cd any-project                     # ideally a git repo with a clean tree
ai init                            # once per project; auto-detects the stack
ai "do something useful"           # run the pipeline
```

## Everyday commands

| Command | What it does |
|---|---|
| `ai "<request>"` | Run the full pipeline (`--with-designer` UI stage · `--with-tester` runs your tests, zero-LLM · `--with-publisher` drafts a commit message · `--fix-loop` auto-fixes once on NEEDS WORK · `--health` injects repowise code-health hotspots, ADR-025) |
| `ai revise "<correction>"` | Iterate on the **last** run without starting over — the Coder resumes its own session and applies the correction, then the Reviewer re-checks (ADR-019) |
| `ai review` | Send the current working-tree diff to the Reviewer — check your own changes with a different model, no pipeline, read-only (ADR-022) |
| `ai publish` | Preview a drafted commit message; `--commit`/`--push` commit (and push) — the only command that runs git, and only when you ask (ADR-020) |
| `ai resume <run-id>` | Continue a failed run from the failed stage — completed stages are never re-paid |
| `ai runs list` / `ai runs show <id>` | Run history: status, per-stage glyphs, cost, verdict |
| `ai ask --role coder "<q>"` | One cheap single-role call, no pipeline |
| `ai doctor` / `ai config show` / `ai init` | Health check · effective config with sources · project setup |

Exit codes: `0` success · `1` a stage failed · `2` config/usage error.

**What the cost figure means:** the `$` value shown after a run is the provider-reported **API-equivalent** value — if you use subscription plans (Claude Pro/Max, ChatGPT), you are **not charged per run**; the run consumes your plan's included quota instead (that's what session limits are). Only API-key users pay it as a real bill. A typical pipeline run "costs" $0.50–1.50 of quota, dominated by fixed per-stage overhead — so it barely grows with task size.

**Quota control:** for small tasks use `ai ask` (one call, no pipeline); set `providers: {claude: {model: haiku}}` in `.ai/config.yaml` for lighter runs; trim stages per project: `pipeline: {stages: [planner, coder]}`.

More: [docs/MANUAL_TESTING.md](docs/MANUAL_TESTING.md) — every command you can try, with token-cost notes.

## ⚠ Trust model

The Coder stage **edits your repository unattended** (scoped to the project directory). Safety net: run from a clean git tree (warned otherwise), every change is diffable, the Reviewer reports on the actual diff, and no pipeline stage ever commits. Details: [docs/MVP.md](docs/MVP.md) §7, [docs/DECISIONS.md](docs/DECISIONS.md) ADR-007.

**No pipeline stage ever runs `git commit`, `git push`, or any GitHub/remote operation — for any role, in any mode.** This cannot be silently escalated by config or a flag. The optional Publisher stage (`--with-publisher`, off by default) only *drafts* a commit message and PR description as a text file (ADR-014). The **one** command that runs git is `ai publish --commit`/`--push` — a separate, **user-invoked** step (never a role) that shows exactly what it will commit and asks you to confirm first (ADR-020). Nothing reaches your history unless you explicitly ask for it, each time.

## Documentation

| Doc | What's in it |
|---|---|
| [HOW_TO_USE.md](docs/HOW_TO_USE.md) · [🇹🇷 Türkçe](docs/HOW_TO_USE.tr.md) | **Start here** — plain-language user guide |
| [IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) | Vision, goals, milestones, risks |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Layers, adapter contract, context system, verified CLI behavior |
| [DECISIONS.md](docs/DECISIONS.md) | 25 ADRs — why everything is the way it is |
| [PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md) | Repo layout + runtime footprint |
| [TASKS.md](docs/TASKS.md) | 35-task build plan with acceptance criteria |
| [MVP.md](docs/MVP.md) | The first full version, stage by stage |
| [MANUAL_TESTING.md](docs/MANUAL_TESTING.md) | Hands-on test commands per milestone |
| [WORKLOG.md](docs/WORKLOG.md) | Session-by-session history |
| [IDEAS.md](docs/IDEAS.md) | Evaluated ideas — opencode & the zero-LLM floor shipped (ADR-017/018); repowise/MCP context reducer still parked |

## Development

```bash
uv sync
uv run pytest          # unit + contract (recorded real CLI fixtures) + integration (fake provider)
uv run ruff check .
```
