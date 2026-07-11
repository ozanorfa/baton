# AI Coding Orchestrator

A **local-first CLI** that turns multiple AI coding assistants (Claude Code, Codex CLI, Antigravity CLI) into one deterministic development pipeline:

```bash
ai "Add Face ID support to the Flutter application"
```

…runs **Planner** (Codex) → **Designer** (Antigravity, optional) → **Coder** (Claude Code) → **Reviewer** (Codex), forwards each stage's output to the next automatically, preserves every artifact on disk, and prints an execution report with real token counts.

**Not another agent framework:** routing is plain Python from YAML config — no supervisor LLM, no dynamic delegation, zero tokens spent on coordination.

## Status

Milestones **M0–M2 complete** (2026-07-11): full pipeline runs end-to-end with all three real providers. In progress: M3 (role prompt templates, layered context, `ai init`). See [docs/TASKS.md](docs/TASKS.md) for progress and [docs/WORKLOG.md](docs/WORKLOG.md) for history.

## Prerequisites

- macOS, Python ≥3.12, [uv](https://docs.astral.sh/uv/)
- The provider CLIs, installed and authenticated: `claude` (Claude Code), `codex` (Codex CLI), `agy` (Antigravity CLI)

## Install & quickstart

```bash
git clone <this-repo> && cd ai-agent-test
uv tool install --editable .      # installs the global `ai` command

ai doctor                          # verify all providers are healthy
cd any-project
ai "do something useful"           # run the pipeline
```

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
