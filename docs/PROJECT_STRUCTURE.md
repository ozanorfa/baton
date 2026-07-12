# Project Structure — AI Coding Orchestrator

**Status:** Living · updated 2026-07-12 · matches the repo — all planned milestones (M0–M5) built, plus ADR-013 (workspace awareness) and ADR-014 (Publisher role)
**Related docs:** [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) · [ARCHITECTURE.md](ARCHITECTURE.md) · [DECISIONS.md](DECISIONS.md) · [TASKS.md](TASKS.md) · [MVP.md](MVP.md)

Naming: distribution package **`ai-orchestrator`**, import package **`ai_orchestrator`**, console script **`ai`** (all referenced by ADR-009's entry-point group `ai_orchestrator.providers`).

There are two distinct layouts to understand: the **repository** (this codebase) and the **runtime footprint** (what the tool creates inside a *user's* project and home directory).

---

## 1. Repository Layout

```
ai-orchestrator/
├── pyproject.toml              # uv-managed; deps, console script `ai`, entry-point group
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
├── app.py                  # root Typer app; main() rewrites bare `ai "<request>"` → `ai run`
├── commands/
│   ├── run.py              # `ai run "<request>"` — the pipeline (+ --with-designer,
│   │                       #   dirty-git-tree warning)
│   ├── init.py             # `ai init` — bootstrap .ai/ in a project
│   ├── doctor.py           # `ai doctor` — provider health checks
│   ├── runs.py             # `ai runs list|show` — run history
│   ├── resume.py           # `ai resume <run-id>` — continue from the failed stage
│   ├── config_cmd.py       # `ai config show` (merged config + value sources)
│   └── ask.py              # `ai ask --role <role> "<prompt>"` — one-shot escape hatch
└── render.py               # ALL Rich output: progress events, summary/report tables, errors
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
├── base.py                 # ProviderAdapter ABC, Capabilities, Health
├── registry.py             # ProviderRegistry: built-in registration + entry-point discovery
├── claude.py               # ClaudeCodeAdapter
├── codex.py                # CodexAdapter
└── antigravity.py          # AntigravityAdapter (ADR-012)
```

**Responsibility:** everything CLI-vendor-specific — flags, output parsing, token-usage extraction, auth checks — and *nothing* else. Adapters are pure (build `Invocation`, parse `TransportResult`; never spawn processes), which is what makes `tests/contract/` possible. When a vendor changes their CLI (risk R1), the blast radius is exactly one file plus its fixtures.

### 1.6 `transport/` — process mechanics (ARCHITECTURE §3.3, ADR-002, ADR-010)

```
transport/
├── base.py                 # Transport protocol; Invocation, TransportResult dataclasses
└── headless.py             # subprocess.run: argv list, shell=False, prompt via stdin,
                            #   timeout, stdout/stderr capture to run dir
```

**Responsibility:** running processes safely. Knows nothing about AI, roles, or providers. The post-MVP `tmux.py` (observability transport) lands here without touching any other layer.

### 1.7 `config/` — configuration (ARCHITECTURE §4)

```
config/
├── schema.py               # pydantic models: PipelineConfig, RoleConfig, ProviderConfig…
├── loader.py               # merge precedence: flags > env > project > user > defaults;
│                           #   tracks the source of every value for `ai config show`
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

The fake-provider integration suite is the project's main safety net: it exercises the entire engine/run-manager/report path with zero token cost. Real-CLI smoke tests stay manual (`ai doctor` + a scripted demo), never in CI.

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

## 2. Runtime Footprint (what `ai` creates)

### 2.1 In the user's project (created by `ai init` / runs)

```
<user-project>/
└── .ai/
    ├── config.yaml             # project config: pipeline stages, role→provider bindings
    ├── project.md              # Project context layer: stack, conventions (ai init bootstraps
    │                           #   with the stack auto-detected from marker files; user curates —
    │                           #   this file is the token budget's best friend)
    ├── prompts/                # optional per-project role template overrides
    └── runs/
        └── 2026-07-11_1432_a3f9/     # one dir per run (ARCHITECTURE §2.4)
            ├── run.json
            ├── report.json
            ├── artifacts/            # plan.md, design.md, changes.md, review.md
            ├── prompts/              # exact rendered prompt per stage
            └── logs/                 # orchestrator.jsonl + raw provider stdout/stderr
```

`ai init` also appends `.ai/runs/` to the project's `.gitignore` (runs are local history; `config.yaml` and `project.md` are meant to be committed and shared with the team).

### 2.2 In the user's home

```
~/.config/ai-orchestrator/
└── config.yaml             # user-level defaults (provider commands, timeouts, models)
```

XDG-style location, macOS-compatible. No other global state — no caches, no daemon files, no databases (ADR-005).
