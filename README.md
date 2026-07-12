# AI Coding Orchestrator

A **local-first CLI** that turns multiple AI coding assistants (Claude Code, Codex CLI, Antigravity CLI) into one deterministic development pipeline:

```bash
ai "Add Face ID support to the Flutter application"
```

…runs **Planner** (Codex) → **Designer** (Antigravity, optional) → **Coder** (Claude Code) → **Reviewer** (Codex), forwards each stage's output to the next automatically, preserves every artifact on disk, and prints an execution report with real token counts.

**Not another agent framework:** routing is plain Python from YAML config — no supervisor LLM, no dynamic delegation, zero tokens spent on coordination.

## Status

**All planned milestones complete (M0–M5, 2026-07-12).** MVP acceptance passed on a real Flutter app (Face ID feature, reviewer verdict APPROVE WITH NOTES); hardening shipped (`ai resume`, `ai runs`, Ctrl-C safety), workspace awareness landed (ADR-013: established projects get a docs index + read-first instruction; greenfield get propose-structure guidance), and an optional Publisher role (ADR-014: drafts a commit message + PR description on a provider of your choice, independent of the coder — never runs git itself). Next: the post-MVP roadmap (session persistence first). See [docs/TASKS.md](docs/TASKS.md) for progress and [docs/WORKLOG.md](docs/WORKLOG.md) for history.

## Prerequisites

- macOS, Python ≥3.12, [uv](https://docs.astral.sh/uv/)
- The provider CLIs, installed and authenticated: `claude` (Claude Code), `codex` (Codex CLI), `agy` (Antigravity CLI)

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
| `ai "<request>"` | Run the full pipeline (`--with-designer` for the UI stage, `--with-publisher` to draft a commit message + PR description) |
| `ai resume <run-id>` | Continue a failed run from the failed stage — completed stages are never re-paid |
| `ai runs list` / `ai runs show <id>` | Run history: status, per-stage glyphs, cost, verdict |
| `ai ask --role coder "<q>"` | One cheap single-role call, no pipeline |
| `ai doctor` / `ai config show` / `ai init` | Health check · effective config with sources · project setup |

Exit codes: `0` success · `1` a stage failed · `2` config/usage error.

**What the cost figure means:** the `$` value shown after a run is the provider-reported **API-equivalent** value — if you use subscription plans (Claude Pro/Max, ChatGPT), you are **not charged per run**; the run consumes your plan's included quota instead (that's what session limits are). Only API-key users pay it as a real bill. A typical pipeline run "costs" $0.50–1.50 of quota, dominated by fixed per-stage overhead — so it barely grows with task size.

**Quota control:** for small tasks use `ai ask` (one call, no pipeline); set `providers: {claude: {model: haiku}}` in `.ai/config.yaml` for lighter runs; trim stages per project: `pipeline: {stages: [planner, coder]}`.

More: [docs/MANUAL_TESTING.md](docs/MANUAL_TESTING.md) — every command you can try, with token-cost notes.

## ⚠ Trust model

The Coder stage **edits your repository unattended** (scoped to the project directory). Safety net: run from a clean git tree (warned otherwise), every change is diffable, the Reviewer reports on the actual diff, and the tool never commits. Details: [docs/MVP.md](docs/MVP.md) §7, [docs/DECISIONS.md](docs/DECISIONS.md) ADR-007.

## Documentation

| Doc | What's in it |
|---|---|
| [IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) | Vision, goals, milestones, risks |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Layers, adapter contract, context system, verified CLI behavior |
| [DECISIONS.md](docs/DECISIONS.md) | 12 ADRs — why everything is the way it is |
| [PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md) | Repo layout + runtime footprint |
| [TASKS.md](docs/TASKS.md) | 35-task build plan with acceptance criteria |
| [MVP.md](docs/MVP.md) | The first full version, stage by stage |
| [MANUAL_TESTING.md](docs/MANUAL_TESTING.md) | Hands-on test commands per milestone |
| [WORKLOG.md](docs/WORKLOG.md) | Session-by-session history |

## Development

```bash
uv sync
uv run pytest          # unit + contract (recorded real CLI fixtures) + integration (fake provider)
uv run ruff check .
```
