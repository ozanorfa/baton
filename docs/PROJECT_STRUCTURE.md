# Project Structure — AI Coding Orchestrator

**Status:** Living · updated 2026-07-12 · matches the repo — all planned milestones (M0–M5) built, plus ADR-013 (workspace awareness) and ADR-014 (Publisher role)
**Related docs:** [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) · [ARCHITECTURE.md](ARCHITECTURE.md) · [DECISIONS.md](DECISIONS.md) · [TASKS.md](TASKS.md) · [MVP.md](MVP.md)

Naming: distribution package **`ai-orchestrator`**, import package **`ai_orchestrator`**, console script **`batonai`** (all referenced by ADR-009's entry-point group `ai_orchestrator.providers`).

There are two distinct layouts to understand: the **repository** (this codebase) and the **runtime footprint** (what the tool creates inside a *user's* project and home directory).

---

## 1. Repository Layout

```
ai-orchestrator/
├── pyproject.toml              # uv-managed; deps, console script `batonai`, entry-point group
├── uv.lock
├── README.md                   # quickstart; points into docs/
├── .gitignore
├── docs/                       # the six design documents (this set)
│   ├── IMPLEMENTATION_PLAN.md
│   ├── ARCHITECTURE.md
│   ├── DECISIONS.md
│   ├── PROJECT_STRUCTURE.md
│   ├── TASKS.md
│   └── MVP.md
├── src/
│   └── ai_orchestrator/
│       ├── __init__.py         # version only
│       ├── cli/
│       ├── core/
│       ├── context/
│       ├── prompts/
│       ├── providers/
│       ├── transport/
│       ├── config/
│       └── observability/
└── tests/
    ├── unit/
    ├── contract/
    └── integration/
```

`src/` layout (not flat) so tests always run against the *installed* package — import mistakes surface immediately, and packaging stays honest from day one.

Each directory under `src/ai_orchestrator/` maps 1:1 to a layer or component in ARCHITECTURE.md. If a new module doesn't obviously belong to one of them, that's a design smell to resolve before writing it.

### 1.1 `cli/` — entry points (ARCHITECTURE §2.1)

```
cli/
├── app.py                  # root Typer app; main() rewrites bare `batonai "<request>"` → `batonai run`;
│                           #   no-args (with a TTY) → the wizard, ADR-026
├── scan.py                 # ADR-026: scan() observes the workspace (IO);
│                           #   decide() maps that state → wizard steps (PURE, no LLM)
├── wizard.py               # ADR-026: the interactive front door — prompts, then
│                           #   hands off to the same run/revise/review/publish commands
├── model_catalog.py        # ADR-031/033: model suggestions/hints for init + setup —
│                           #   live discovery (`agy models`) where a provider supports it,
│                           #   a static fallback otherwise; never validated (ADR-031)
├── commands/
│   ├── run.py              # `batonai run "<request>"` — the pipeline (+ --with-designer,
│   │                       #   dirty-git-tree / no-baseline-commit warnings, ADR-029)
│   ├── init.py             # `batonai init` — bootstrap .ai/ in a project; offers a
│   │                       #   model choice per provider (ADR-031)
│   ├── setup.py            # `batonai setup` — revise role→provider and provider→model
│   │                       #   at any time; merges into .ai/config.yaml (ADR-032)
│   ├── doctor.py           # `batonai doctor` — provider health checks
│   ├── health.py           # `batonai health` — print the repowise code-health slice
│   │                       #   on demand, zero tokens (cached per project, ADR-028)
│   ├── runs.py             # `batonai runs list|show` — run history
│   ├── resume.py           # `batonai resume <run-id>` — continue from the failed stage
│   ├── revise.py           # `batonai revise "<correction>"` — continue the last run,
│   │                       #   Coder resumes its own session (ADR-019)
│   ├── review.py           # `batonai review` — Reviewer over the current diff, read-only
│   │                       #   and pipeline-free (ADR-022)
│   ├── publish.py          # `batonai publish` — draft/commit/push, the one command
│   │                       #   that ever runs git, and only on explicit flags (ADR-020)
│   ├── config_cmd.py       # `batonai config show` (merged config + value sources)
│   └── ask.py              # `batonai ask --role <role> "<prompt>"` — one-shot escape hatch
└── render.py               # ALL Rich output: progress events (incl. ADR-030's live notes),
                            #   summary/report tables, the wizard's scan report, errors
```

**Responsibility:** argument parsing, config loading, delegation, rendering. **Zero business logic** — every command body should read as "parse → call core → render". `render.py` centralizes Rich so the core stays terminal-agnostic (a future MCP entry layer reuses the core untouched, ARCHITECTURE §7).

### 1.2 `core/` — orchestration (ARCHITECTURE §2.2–2.5)

```
core/
├── models.py               # pydantic types shared across layers: StageSpec, StageResult,
│                           #   RunState, AgentRequest, AgentResult, Report
├── engine.py               # PipelineEngine: the sequential stage loop, fail-stop semantics
├── routing.py              # RoutingEngine: role → adapter resolution + upfront health checks
├── run_manager.py          # RunManager: run-id, run dir creation, atomic run.json writes,
│                           #   artifact persistence, resume loading
├── workspace.py            # git change detection for edit-stages: diff.patch capture +
│                           #   silent-failure (permission-block) detection; excludes .ai/
└── reporter.py             # Reporter: report.json + data for the terminal summary
```

**Responsibility:** everything deterministic about a run. Depends only on `providers/base`, `context/`, `config/`, `observability/`. **Never imports a concrete adapter or anything from `transport/`** — the two rules from ARCHITECTURE §1 are enforced as import discipline here (and checked by a lint rule in CI later).

`models.py` is the shared vocabulary of the system; it has no imports from other project modules, so any layer may import it without cycles.

### 1.3 `context/` — context assembly (ARCHITECTURE §5)

```
context/
├── manager.py              # ContextManager: assemble(stage) → rendered prompt sections
├── layers.py               # Global / Project / Task / Agent layer sources
├── awareness.py            # ADR-013: established/greenfield detection, capped repo map,
│                           #   docs index — the Workspace layer
├── health.py               # ADR-025: optional repowise code-health hotspot slice (opt-in)
└── contracts.py            # per-stage input contracts (what each role may receive)
```

**Responsibility:** the *only* place the minimal-context principle is enforced (risk R4). `contracts.py` is data, not logic — the table from ARCHITECTURE §5 as code, so a contract change is a one-line diff with an obvious review surface.

### 1.4 `prompts/` — built-in role templates (package data)

```
prompts/
├── planner.md              # role definition + output format ("self-contained plan", ADR-006)
├── designer.md
├── coder.md
├── reviewer.md
└── publisher.md            # ADR-014: drafts commit message + PR description, never runs git
```

**Responsibility:** the Agent context layer. Markdown with named placeholder sections filled by `ContextManager`. Shipped as package data; overridable per project via `.ai/prompts/<role>.md` (ADR-009). Templates are versioned artifacts — prompt changes are code-reviewed like code, because they *are* behavior.

### 1.5 `providers/` — adapters (ARCHITECTURE §3)

```
providers/
├── base.py              # ProviderAdapter ABC, Capabilities, Health, progress_note()
│                        #   default (ADR-030) and the shared _sanitize() for untrusted
│                        #   provider text rendered to a terminal
├── registry.py          # ProviderRegistry: built-in registration + entry-point discovery
├── claude.py             # ClaudeCodeAdapter — the Coder's usual provider
├── codex.py              # CodexAdapter — implements progress_note() from `--json`
│                         #   item.started/completed events (ADR-030)
├── antigravity.py        # AntigravityAdapter (ADR-012) — the Designer's provider
├── opencode.py           # OpencodeAdapter (ADR-017) — free-tier client, Publisher only
├── deterministic.py      # DeterministicAdapter (ADR-018) — zero-LLM Publisher floor,
│                         #   a conventional-commit message from `git diff --stat`
└── testrunner.py         # TestRunnerAdapter (ADR-024) — zero-LLM Tester, runs the
                          #   project's own test command and reports pass/fail
```

**Responsibility:** everything CLI-vendor-specific — flags, output parsing, token-usage extraction, auth checks — and *nothing* else. Adapters are pure (build `Invocation`, parse `TransportResult`; never spawn processes), which is what makes `tests/contract/` possible. When a vendor changes their CLI (risk R1), the blast radius is exactly one file plus its fixtures.

### 1.6 `transport/` — process mechanics (ARCHITECTURE §3.3, ADR-002, ADR-010)

```
transport/
├── base.py                 # Transport protocol; Invocation, TransportResult dataclasses
└── headless.py             # subprocess.run: argv list, shell=False, prompt via stdin,
                            #   timeout, stdout/stderr capture; plus an opt-in streaming
                            #   path (ADR-030) — Popen + line reads, watchdog timeout
                            #   timeout, stdout/stderr capture to run dir
```

**Responsibility:** running processes safely. Knows nothing about AI, roles, or providers. The post-MVP `tmux.py` (observability transport) lands here without touching any other layer.

### 1.7 `config/` — configuration (ARCHITECTURE §4)

```
config/
├── schema.py               # pydantic models: PipelineConfig, RoleConfig, ProviderConfig…
├── loader.py               # merge precedence: flags > env > project > user > defaults;
│                           #   tracks the source of every value for `batonai config show`
└── defaults.yaml           # built-in defaults (the lowest precedence layer)
```

**Responsibility:** producing one validated, typed, source-annotated config object. Fail fast at load with the offending file and key. No other module reads YAML or environment variables — ever.

### 1.8 `observability/` — logging (ARCHITECTURE §6)

```
observability/
└── events.py               # structured JSONL event log (stage_started, provider_invoked,
                            #   stage_failed…) writing to <run-dir>/logs/orchestrator.jsonl
```

**Responsibility:** the machine-readable event stream. Human-facing output lives in `cli/render.py`, not here — one event source, two renderings.

### 1.9 `tests/`

```
tests/
├── unit/                   # mirrors src/ layout: engine, routing, config merge, context
│                           #   contracts, run_manager state transitions — no subprocesses
├── contract/               # adapter parse()/build_invocation() vs recorded REAL CLI outputs
│   └── fixtures/
│       ├── claude/         # captured `claude -p --output-format json` outputs
│       │                   #   (success, failure, permission-block, malformed)
│       ├── codex/
│       └── antigravity/
└── integration/            # full pipeline against a FAKE provider CLI — fast, free,
    │                       #   deterministic, no real AI calls
    └── fake_provider/      # fake_ai.py (CLI driven by prompt directives like
                            #   [[fail:msg]]) + fakeplug.py adapter + a COMMITTED
                            #   dist-info so discovery runs through the real
                            #   entry-point mechanism (no test-only paths in src/)
```

The fake-provider integration suite is the project's main safety net: it exercises the entire engine/run-manager/report path with zero token cost. Real-CLI smoke tests stay manual (`batonai doctor` + a scripted demo), never in CI.

### 1.10 Dependency directions (enforced)

| Module | May import |
|---|---|
| `cli/` | `core`, `config`, `observability` |
| `core/` | `providers/base`, `context`, `config`, `observability`, `models` |
| `context/` | `config`, `models` |
| `providers/` | `transport/base`, `models` |
| `transport/` | stdlib only |
| `config/`, `observability/` | `models`, stdlib |

Anything pointing the other way is a bug.

---

## 2. Runtime Footprint (what `batonai` creates)

### 2.1 In the user's project (created by `batonai init` / runs)

```
<user-project>/
└── .ai/
    ├── config.yaml             # project config: pipeline stages, role→provider bindings
    │                           #   (editable by hand, or via `batonai setup`, ADR-032)
    ├── project.md              # Project context layer: stack, conventions (batonai init bootstraps
    │                           #   with the stack auto-detected from marker files; user curates —
    │                           #   this file is the token budget's best friend)
    ├── .gitignore              # ignores runs/ and health.json (ADR-027) — never the project's
    │                           #   own root .gitignore, which baton does not touch
    ├── health.json             # per-project code-health cache (ADR-028): the rendered
    │                           #   repowise slice + raw KPIs, refreshed when a source file
    │                           #   is newer than it or it turns 7 days old
    ├── prompts/                # optional per-project role template overrides
    └── runs/
        └── 2026-07-11_1432_a3f9/     # one dir per run (ARCHITECTURE §2.4)
            ├── run.json
            ├── report.json
            ├── artifacts/            # plan.md, design.md, changes.md, review.md
            ├── prompts/              # exact rendered prompt per stage
            └── logs/                 # orchestrator.jsonl + raw provider stdout/stderr
```

`config.yaml` and `project.md` are meant to be committed and shared with the team; `.gitignore`, `health.json` and `runs/` are local state and stay out of version control. **The project's root `.gitignore` is never touched** (ADR-027) — baton edits only files it owns, so its own bookkeeping can never show up as part of the Coder's diff. A project set up by an older baton (which did append to the root `.gitignore`) keeps that entry and gains no duplicate.

### 2.2 In the user's home

```
~/.config/ai-orchestrator/
└── config.yaml             # user-level defaults (provider commands, timeouts, models)
```

XDG-style location, macOS-compatible. No other global state — no caches, no daemon files, no databases (ADR-005).
