# Architecture — AI Coding Orchestrator

**Status:** Living · updated 2026-07-11 · fully implemented, M0–M5 (adapter table below reflects *verified* CLI behavior, not assumptions)
**Related docs:** [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) · [DECISIONS.md](DECISIONS.md) · [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) · [TASKS.md](TASKS.md) · [MVP.md](MVP.md)

---

## 1. Overall Architecture

Four layers with strict downward-only dependencies. Every AI-CLI-specific detail is confined to the provider layer; every process-mechanics detail is confined to the transport layer.

```
┌─────────────────────────────────────────────────────────────┐
│  CLI Layer (Typer + Rich)                                   │
│  ai "<request>" · ai init · ai doctor · ai runs ·           │
│  ai resume · ai config · ai ask                             │
├─────────────────────────────────────────────────────────────┤
│  Orchestration Core                                         │
│  PipelineEngine · RoutingEngine · ContextManager ·          │
│  RunManager · Reporter                                      │
├─────────────────────────────────────────────────────────────┤
│  Provider Layer                                             │
│  ProviderRegistry → ProviderAdapter (ABC)                   │
│  ├─ ClaudeCodeAdapter    (claude -p --output-format json)   │
│  ├─ CodexAdapter         (codex exec)                       │
│  └─ AntigravityAdapter   (agy -p)                           │
├─────────────────────────────────────────────────────────────┤
│  Transport Layer                                            │
│  HeadlessTransport (subprocess)  ·  [post-MVP] TmuxTransport│
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
              Disk state: .ai/runs/<run-id>/
              (artifacts, prompts, logs, report)
```

**Rules that keep the architecture honest:**

- The core never imports a concrete adapter; it talks to `ProviderAdapter` only.
- Adapters never spawn processes themselves; they build an `Invocation` (argv, stdin, env, timeout) and hand it to a transport.
- No component holds run state in memory only — every state transition is persisted to the run directory first (crash-safe, resumable, inspectable).
- No LLM ever makes a routing decision.

## 2. Components

### 2.1 CLI Layer

Typer application, Rich for output. Thin by design: parses arguments, loads config, delegates to the core, renders results. No business logic.

| Command | Purpose |
|---|---|
| `ai "<request>"` | Run the configured pipeline on a request |
| `ai init` | Bootstrap `.ai/` in a project (config + project profile; the profile's Stack section is pre-filled by auto-detecting marker files — pubspec.yaml, package.json, pyproject.toml, go.mod, …) |
| `ai doctor` | Verify every configured provider: binary found, version, authenticated |
| `ai runs list` / `ai runs show <id>` | Run history and inspection |
| `ai resume <run-id>` | Continue a failed run from its failed stage (`--with-designer`/`--with-publisher` to keep optional stages enabled) |
| `ai config show` | Print merged effective configuration and its sources |
| `ai ask --role <role> "<prompt>"` | One-shot single-role invocation (debugging/utility) |

### 2.2 Pipeline Engine

The heart of the system, and deliberately boring: a sequential interpreter over a static stage list.

```python
@dataclass(frozen=True)
class StageSpec:
    name: str            # "planner", "designer", "coder", "reviewer"
    role: str            # role key → prompt template + input contract
    optional: bool       # e.g. designer: skipped unless enabled
    inputs: list[str]    # artifact names consumed, e.g. ["plan"]
    output: str          # artifact name produced, e.g. "code_changes"
```

Execution loop (pseudocode):

```
for stage in pipeline.stages:                 # order comes from config, never runtime logic
    if stage.optional and not enabled(stage): # explicit config/flag, not inference
        record_skipped(stage); continue
    adapter  = routing.resolve(stage.role)    # role → provider binding
    context  = context_mgr.assemble(stage)    # minimal layered context
    prompt   = templates.render(stage.role, context, inputs)
    result   = adapter.invoke(Invocation(prompt, workdir, timeout))
    persist(stage, prompt, result)            # before anything else
    if result.failed:
        report.fail(stage, result); STOP      # fail-stop: log, preserve, halt
    artifacts[stage.output] = result.artifact
```

MVP semantics: **no retries, no escalation, no parallelism, no reordering.** A failed stage stops the run; the report tells the user exactly what to inspect and how to resume.

*Implementation note:* the engine emits events to an optional live sink consumed by the CLI's progress rendering. Since M3, contracts live in `context/contracts.py` and prompts are assembled by `context/manager.py` as designed in §5.

### 2.3 Routing Engine

Pure function from config: `role → provider adapter instance`. Resolution order:

1. Per-run CLI override (`--provider coder=claude`) — highest
2. Project config (`.ai/config.yaml`)
3. User config (`~/.config/ai-orchestrator/config.yaml`)
4. Built-in defaults

At run start, the routing engine resolves **all** stages up front and health-checks each distinct provider once — a pipeline never fails at stage 3 because of something `ai doctor` could have caught before stage 1.

### 2.4 Run Manager

Owns the run directory and the run state machine.

```
.ai/runs/2026-07-11_1432_a3f9/
├── run.json               # state machine: request, stages, statuses, timings
├── report.json            # final execution report (Reporter output)
├── artifacts/
│   ├── plan.md             # Planner output
│   ├── design.md           # Designer output (if stage enabled)
│   ├── changes.md          # Coder summary of edits (code lands in the repo itself)
│   ├── diff.patch          # git diff snapshot of the Coder's edits
│   └── review.md           # Reviewer output
├── prompts/                # exact prompt sent to each stage (audit/debug)
│   ├── 01-planner.md
│   └── ...
└── logs/
    ├── orchestrator.jsonl  # structured event log
    └── 03-coder.stderr     # raw provider stderr per stage
```

Stage statuses: `pending → running → succeeded | failed | skipped`. `run.json` is rewritten atomically on every transition, which is what makes `ai resume` possible: resume = load `run.json`, keep succeeded artifacts, re-enter the loop at the failed stage.

### 2.5 Reporter

Aggregates per-stage data into `report.json` + a Rich terminal summary: stage, provider, model (when reported), duration, token usage (measured when the CLI reports it — Claude's JSON output does — otherwise `null`, never guessed), status, artifact paths. Cost figures carry a standing note (terminal footnote + `cost_note` field in report.json): they are the provider-reported API-equivalent value — subscription plans consume quota, they are not billed per run.

## 3. Provider Layer

### 3.1 Adapter contract

```python
class ProviderAdapter(ABC):
    name: str                          # "claude", "codex", "antigravity"
    capabilities: Capabilities         # supports_resume, reports_tokens, edits_files

    @abstractmethod
    def health_check(self) -> Health: ...          # binary present, version, auth OK
    @abstractmethod
    def build_invocation(self, req: AgentRequest) -> Invocation: ...
    @abstractmethod
    def parse(self, raw: TransportResult) -> AgentResult: ...
```

`AgentResult` carries: `text` (the payload), `success`, `session_id` (if the CLI returns one — stored for future resume), `usage` (tokens/cost or `None`), `raw_path` (full raw output on disk).

The split between `build_invocation` and `parse` keeps adapters **pure and unit-testable**: feed a recorded fixture of real CLI output into `parse()` — no subprocess needed. This is the primary defense against risk R1 (CLI drift): each adapter ships contract tests against recorded real outputs.

### 3.2 Concrete adapters (verified against real CLIs, 2026-07-11)

| Adapter | Invocation | Output | Tokens | Session | Verified quirks |
|---|---|---|---|---|---|
| **ClaudeCodeAdapter** (claude 2.1.207) | `claude -p --output-format json`, prompt on stdin | Structured JSON: result, `session_id`, usage, cost | ✅ measured + cost | ✅ `session_id` (`--resume`) | Edit-roles get `--permission-mode acceptEdits`. **A permission-blocked run exits 0 with `is_error:false`** — protocol-invisible; only the stage-level diff check catches it (T26) |
| **CodexAdapter** (codex-cli 0.144.1) | `codex exec --json --skip-git-repo-check -s <sandbox> -`, prompt on stdin | JSONL events | ✅ measured (`turn.completed`) | ✅ `thread_id` (`codex exec resume`) | Sandbox maps to role write-access: `read-only` for Planner/Reviewer, `workspace-write` for edit-roles — role separation enforced by the OS sandbox, not just prompts |
| **AntigravityAdapter** (agy 1.1.1) | `agy --print-timeout <t>s -p <prompt>` | Plain text | ❌ none reported | ❌ id not printed in `-p` mode | **No stdin prompt support** → argv exception to ADR-010 (amended). `--sandbox` is incompatible with print mode. `--print-timeout` (default 5m) pinned to request timeout |

Prompt payloads are passed via **stdin, not argv** (shell-escaping and length safety) — except Antigravity, which cannot read stdin (ADR-010 amendment).

### 3.3 Session management

**MVP:** every invocation is one-shot headless. Context continuity between stages comes from **artifacts, not sessions** — the Coder reads `plan.md`, not the Planner's conversation.

The seam for post-MVP session persistence exists from day one: adapters record `session_id` in `run.json` when the CLI returns one, and `Capabilities.supports_resume` marks who can use it. Post-MVP, the engine passes the prior `session_id` back (`claude -p --resume <id>`, `codex exec resume`), cutting repeated project context — the largest token win on the roadmap. tmux, when it arrives, is a **TmuxTransport for observability** (watch a live pane); parsing always comes from the headless JSON path, never from scraping panes (see DECISIONS.md ADR-002).

### 3.4 Plugin architecture

Adding a provider must never touch core code (goal G5):

1. **Built-ins** live in `providers/` and self-register with the `ProviderRegistry`.
2. **External plugins** register via the Python entry-point group `ai_orchestrator.providers`; any installed package can contribute an adapter. The registry discovers entry points at startup.
3. Config refers to providers **by name only** — `coder: {provider: claude}`. An unknown name yields an actionable error listing registered providers.

Role prompt templates are equally pluggable: built-in templates in the package, overridable per-project in `.ai/prompts/<role>.md`.

## 4. Configuration System

YAML, merged with clear precedence (highest wins):

```
CLI flags  >  env vars (AI_ORCH_*)  >  ./.ai/config.yaml  >  ~/.config/ai-orchestrator/config.yaml  >  built-in defaults
```

```yaml
# .ai/config.yaml (project)
pipeline:
  stages: [planner, designer, coder, reviewer]   # order is normative

roles:
  planner:  { provider: codex }
  designer: { provider: antigravity, enabled: false } # optional stage, off by default
  coder:    { provider: claude }
  reviewer: { provider: codex }

providers:
  claude:      { command: claude, model: null, timeout_s: 900 }
  codex:       { command: codex,  timeout_s: 600 }
  antigravity: { command: agy,    timeout_s: 600 }

context:
  project_profile: .ai/project.md    # written by `ai init`
```

Validated at load time into typed objects (pydantic): unknown keys warn, invalid values fail fast with the file and key that caused it. `ai config show` prints the merged result annotated with the source of each value. Changing any provider is a config edit — never a code change (goal G5, principle 6).

## 5. Context Management

Four layers, assembled per stage by the `ContextManager` — the single place where the minimal-context principle is enforced (defense against risk R4):

| Layer | Content | Lifetime | Example |
|---|---|---|---|
| **Global** | Orchestrator conventions: output format rules, artifact expectations | Static | "Write your plan as markdown with numbered steps" |
| **Project** | Tech stack, structure, conventions — from `.ai/project.md` (`ai init`) | Per project | "Flutter 3.x app, Riverpod, feature-first layout" |
| **Workspace** (ADR-013) | Deterministic maturity detection: *established* → capped repo map + docs index (README/docs/*.md) + read-first instruction; *greenfield* → propose-structure guidance. Documents are indexed, never inlined | Computed per run | "Project documents (read the relevant ones first): README.md — Habit App…" |
| **Task** | The user request + accumulated stage artifacts *per input contract* | Per run | The request + `plan.md` |
| **Agent** | Role definition and boundaries | Static per role | "You are the Reviewer. Do not rewrite code; report findings." |

**Per-stage input contracts** — each role receives only what its stage consumes:

| Stage | Receives | Does *not* receive |
|---|---|---|
| Planner | request + Project | — |
| Designer | request + Project + plan | — |
| Coder | plan (+ design) + Project; explores the repo itself via its own tools | Planner transcript, request restatement |
| Reviewer | plan + coder's change summary + `git diff` of the run | design detail, full file contents already in the diff |

Two structural token savers: the Coder is the only stage that touches the codebase directly (Claude Code explores with its own tools — the orchestrator never inlines source files into prompts), and downstream stages get **artifacts, not transcripts**.

## 6. Logging & Observability

- **Structured event log** — `logs/orchestrator.jsonl` per run: one JSON line per event (`stage_started`, `provider_invoked`, `stage_failed`, …) with timestamps and durations. Machine-readable for future tooling.
- **Human console** — Rich: live stage progress during the run, summary table at the end.
- **Raw provider output** — stdout/stderr per stage preserved verbatim in `logs/`; when parsing fails, the raw material is always on disk.
- **Prompt audit** — the exact rendered prompt per stage in `prompts/`. Answers "why did the Coder do that?" and makes token spending inspectable.
- Global (cross-run) logging stays out of MVP; the per-run directory is the unit of observability.

## 7. Future: MCP Integration

Two directions, both post-MVP, both compatible with this architecture:

1. **Orchestrator as MCP server** — expose `run_pipeline`, `get_run_status`, `list_runs` as MCP tools so IDEs/other agents can trigger pipelines. Sits beside the Typer CLI as a second thin entry layer over the same core — no core changes.
2. **MCP as context source** — the ContextManager gains MCP-backed context providers (issue trackers, docs) feeding the Project/Task layers. A new context source, not a new architecture.

## 8. Future: Memory System

Per-project persistent knowledge in `.ai/memory/`: decisions made in past runs, learned conventions, past review findings. Feeds the **Project** context layer (bounded, curated, summarized — never raw transcripts). Also enables "the Reviewer flagged this pattern before" continuity. Deliberately unimplemented until real usage shows which memories earn their token cost.

## 9. What This Architecture Deliberately Avoids

| Avoided | Because |
|---|---|
| Supervisor/orchestrator agent (CAO's model) | Routing via LLM costs tokens and determinism — the two things this project exists to protect |
| Message bus / event-driven core | Sequential pipeline needs a for-loop, not an event system |
| Server process + DB (FastAPI/SQLite) | Local-first single command; the filesystem is the database, the run directory is the schema |
| tmux pane-scraping as transport | Heuristic completion detection is the flakiest part of CAO; headless JSON is deterministic |
| Streaming stage-to-stage piping | Artifacts on disk are inspectable, resumable, and debuggable; streaming buys nothing in a sequential pipeline |
