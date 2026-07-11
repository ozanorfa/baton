# Architectural Decision Records — AI Coding Orchestrator

**Status:** Draft v1 · 2026-07-11
**Related docs:** [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) · [ARCHITECTURE.md](ARCHITECTURE.md) · [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) · [TASKS.md](TASKS.md) · [MVP.md](MVP.md)

Convention: one ADR per consequential decision. New decisions get new ADRs; reversals supersede, never rewrite history. Any future proposal for dynamic/LLM-driven orchestration **requires** an ADR here before code (risk R7 guard).

| # | Decision | Status |
|---|----------|--------|
| [ADR-001](#adr-001) | Do not build on Amazon CAO; borrow its patterns | Accepted |
| [ADR-002](#adr-002) | Headless-first transport; tmux deferred to observability | Accepted (supersedes spec §8) |
| [ADR-003](#adr-003) | Codex CLI as the OpenAI provider vehicle | Accepted |
| [ADR-004](#adr-004) | Orchestration is deterministic code, never an LLM | Accepted |
| [ADR-005](#adr-005) | Filesystem is the state store — no server, no database | Accepted |
| [ADR-006](#adr-006) | Stages hand off artifacts, not sessions or transcripts | Accepted |
| [ADR-007](#adr-007) | Coder runs headless with scoped auto-edit permissions | Accepted |
| [ADR-008](#adr-008) | Fail-stop error handling in MVP | Accepted |
| [ADR-009](#adr-009) | Provider plugins via entry points; config binds by name | Accepted |
| [ADR-010](#adr-010) | Prompts delivered via stdin, never argv | Accepted |
| [ADR-011](#adr-011) | Stack: Python 3.12 + uv + Typer + Rich + pydantic + YAML | Accepted |
| [ADR-012](#adr-012) | Antigravity CLI replaces Gemini CLI as the Designer provider | Accepted |

---

## ADR-001 — Do not build on Amazon CAO; borrow its patterns

**Status:** Accepted · 2026-07-11

**Context.** The spec asked whether [awslabs/cli-agent-orchestrator](https://github.com/awslabs/cli-agent-orchestrator) (CAO) could serve as a foundation. CAO genuinely orchestrates coding CLIs (Claude Code, Codex, Cursor, Kiro…) in tmux sessions and is actively maintained.

**Decision.** Build our own thin core; treat CAO as reference material only.

**Why.**
1. *Inverted control model.* CAO's orchestration is agent-driven: an LLM supervisor decides delegation at runtime via MCP handoff/inbox tools. Our requirement is a deterministic, code-driven pipeline — CAO's central abstraction is the thing we must not have. Adopting it means fighting the framework at its core.
2. *Heavyweight runtime.* FastAPI server (port 9889), SQLite, event bus, web dashboard — permanent infrastructure a single-command local CLI doesn't need.
3. *Coordination costs tokens.* CAO's supervisor spends model tokens deciding who works next; our router is free Python. This alone conflicts with a top-line goal.

**Alternatives considered.** (a) Fork CAO and strip the supervisor — rejected: what remains after removing supervisor+server+bus is roughly the adapter layer, which is the easy 20%. (b) Use CAO as a dependency for its tmux layer — rejected in the MVP because ADR-002 removes tmux from the critical path.

**Trade-offs.** We re-implement provider adapters and session mechanics ourselves; we forgo CAO's community fixes for CLI quirks.

**Future implications.** When the post-MVP tmux observability layer is built, CAO's mechanics (bracketed-paste input, FIFO output streaming, per-CLI idle detection) are the proven reference to copy from.

---

## ADR-002 — Headless-first transport; tmux deferred to observability

**Status:** Accepted · 2026-07-11 · **Supersedes spec §8 (tmux session management). Confirmed with the project owner.**

**Context.** The original spec mandated persistent tmux sessions per CLI, with the orchestrator sending keystrokes and scraping pane output. But every target CLI has a non-interactive mode: `claude -p --output-format json` (structured result, session id, measured token usage/cost), `codex exec`, `gemini -p`.

**Decision.** Provider invocations run headless via subprocess. Stdout/exit codes are the completion signal; JSON is parsed where offered. tmux is deferred to a post-MVP *observability* layer (watch a live pane) and will never be the parsing mechanism.

**Alternatives considered.** (a) tmux-first as specified — rejected: completion detection becomes per-CLI idle heuristics (the flakiest part of CAO), output parsing becomes ANSI-scraping, and token usage is unmeasurable. (b) Hybrid from day one (tmux only for the Coder) — rejected for MVP: two transport code paths double the surface area for the least mature part of the system.

**Trade-offs.** We lose warm persistent sessions in the MVP — each invocation pays session startup and cold context. Mitigated by artifact-based handoff (ADR-006) and recovered post-MVP via `--resume`/`codex exec resume` session persistence, which delivers the same token savings tmux persistence promised, without scraping.

**Future implications.** The `Transport` seam is designed so `TmuxTransport` can be added without touching adapters or the engine. Session ids are recorded from day one so resume needs no schema change.

---

## ADR-003 — Codex CLI as the OpenAI provider vehicle

**Status:** Accepted · 2026-07-11 · **Confirmed with the project owner.**

**Context.** The spec assigns Planner and Reviewer to "OpenAI GPT", but no official general-purpose GPT CLI exists. The realistic vehicles are Codex CLI (`codex exec`) or direct OpenAI API calls.

**Decision.** Use Codex CLI. Every provider is then uniformly "a CLI subprocess", one adapter model covers all three providers, and usage rides the user's existing ChatGPT subscription rather than separate API billing.

**Alternatives considered.** (a) OpenAI API direct — cleaner structured outputs (JSON mode) but introduces a second adapter style (HTTP vs subprocess), API-key management, and separate billing in the MVP. (b) Both adapters — most flexible, rejected as MVP scope growth.

**Trade-offs.** Codex CLI output is less structured than the raw API; token usage may be unavailable (report shows `null`, never a guess — risk R2). Plan/review output quality depends on prompt-template discipline rather than JSON mode.

**Future implications.** An `OpenAIApiAdapter` remains a legitimate future plugin — the adapter contract does not assume subprocess transport is the only kind; an adapter could build an HTTP-backed invocation. Nothing in config or core would change: `planner: {provider: openai-api}`.

---

## ADR-004 — Orchestration is deterministic code, never an LLM

**Status:** Accepted · 2026-07-11

**Context.** The dominant industry pattern (CAO, CrewAI, AutoGen) puts a model in charge of routing. The spec explicitly rejects this; this ADR records *why*, so the decision survives future "just let the model decide" temptations.

**Decision.** Stage order, stage skipping, provider selection, failure handling — all decided by Python from config. No model output ever alters control flow. The only sanctioned "dynamic" element is config/flag-gated optionality (e.g. the Designer stage).

**Alternatives considered.** (a) Supervisor agent — rejected: token cost for coordination, non-reproducible runs, undebuggable failures. (b) LLM-based *classification* only (model picks which pipeline variant fits the request) — rejected for MVP; if ever added, it must be an isolated, logged, overridable pre-step with its own ADR.

**Trade-offs.** Less flexible on unusual requests: the pipeline runs Planner→Coder→Reviewer even when a human might skip planning for a trivial fix. Accepted: predictability is the product. (`ai ask --role coder` exists as the manual escape hatch.)

**Future implications.** Retries/escalation (post-MVP) must also be policy-from-config, not model judgment. This ADR is the reference to cite when rejecting dynamic-orchestration proposals (risk R7).

---

## ADR-005 — Filesystem is the state store — no server, no database

**Status:** Accepted · 2026-07-11

**Context.** Run state, artifacts, logs, and reports need persistence. CAO uses SQLite + a FastAPI server; many frameworks assume a daemon.

**Decision.** All state lives in `.ai/runs/<run-id>/` as plain files (`run.json` state machine, markdown artifacts, JSONL logs). `run.json` is rewritten atomically on every stage transition. No background process; each `ai` invocation is a complete, self-contained program run.

**Alternatives considered.** (a) SQLite — better queryability across runs, rejected for MVP: adds a schema and migration surface for data a human primarily wants to *read as files*. (b) Daemon process — rejected: local-first means nothing running when you're not.

**Trade-offs.** Cross-run analytics require walking directories (fine at local scale). Concurrent runs in the same project need distinct run dirs (already guaranteed by run-id) — no locking needed in a no-parallelism MVP.

**Future implications.** Crash-safety and `ai resume` fall directly out of this design. If cross-run querying ever matters, an *index* (even SQLite) can be added as a cache over the files — files stay the source of truth.

---

## ADR-006 — Stages hand off artifacts, not sessions or transcripts

**Status:** Accepted · 2026-07-11

**Context.** "Shared context" (spec §4) could mean forwarding conversation transcripts between stages, sharing a session, or passing distilled artifacts. Naive transcript-forwarding grows context every stage and defeats the token goal (risk R4).

**Decision.** Each stage produces a named artifact (`plan.md`, `design.md`, `changes.md`, `review.md`); downstream stages receive artifacts per an explicit input contract (see ARCHITECTURE.md §5). Two hard rules: the orchestrator never inlines repo source files into prompts (only the Coder touches the codebase, with its own tools), and no stage ever sees another stage's transcript.

**Alternatives considered.** (a) Transcript forwarding — rejected: unbounded growth, noise poisons downstream stages. (b) One shared session across all stages — impossible across different vendors' CLIs, and would violate single-responsibility role boundaries anyway.

**Trade-offs.** Information loss at each handoff is real: if the Planner's reasoning matters to the Reviewer, it must be *in the plan*. Prompt templates therefore instruct roles to write self-contained artifacts.

**Future implications.** Artifacts double as the human review surface and the resume mechanism. The future memory system (ARCHITECTURE.md §8) follows the same rule: distilled knowledge in, transcripts never.

---

## ADR-007 — Coder runs headless with scoped auto-edit permissions

**Status:** Accepted · 2026-07-11

**Context.** The Coder stage must modify the repo. Headless Claude Code will stall (or abort) if it hits an interactive permission prompt mid-run.

**Decision.** The Coder is invoked with an explicit, scoped permission mode (e.g. `claude -p --permission-mode acceptEdits`) allowing file edits within the project directory without interaction. The trust model is stated openly: **the Coder edits your repo unattended**; the safety net is layered — git (every run's changes are diffable and revertible), the Reviewer stage (reviews the actual `git diff`), and fail-stop (nothing proceeds past a failure).

**Alternatives considered.** (a) Plan-only Coder that emits patches for the orchestrator to apply — rejected: discards Claude Code's core strength (iterative explore-edit-verify with its own tools) and turns the orchestrator into a patch engine. (b) Interactive approval mid-pipeline — rejected for MVP: reintroduces the manual babysitting the project exists to remove. (c) Full `--dangerously-skip-permissions` — rejected: broader than needed; edits scoped to the project are sufficient.

**Trade-offs.** Users must accept unattended edits (documented prominently). A run should start from a clean git state so the run's diff is unambiguous — `ai` warns on a dirty working tree.

**Future implications.** Post-MVP could add an opt-in "gated mode" (pipeline pauses after Coder for human approval before Review). A future sandbox/worktree isolation mode is compatible: run the Coder in a git worktree, merge on approval.

---

## ADR-008 — Fail-stop error handling in MVP

**Status:** Accepted · 2026-07-11

**Context.** Any stage can fail: CLI crash, timeout, auth expiry, unparseable output, model refusal.

**Decision.** On failure: persist everything already produced, write a failure report naming the stage, cause, and raw-output path, halt, and print exactly how to continue (`ai runs show <id>`, `ai resume <id>`). No retries, no fallback provider, no skipping ahead.

**Alternatives considered.** (a) Auto-retry N times — rejected for MVP: retries without diagnosis burn tokens on repeatable failures (bad prompt, expired auth) and mask flakiness we need to see during hardening. (b) Provider fallback — rejected: silently switching the Coder's model mid-run makes results unexplainable.

**Trade-offs.** Transient failures (network blips) that a retry would absorb instead stop the run. Acceptable while we learn the actual failure distribution; M5's structured logs exist to inform the eventual retry policy.

**Future implications.** Post-MVP retries/escalation arrive as *config-defined policy* (per ADR-004) once real failure data justifies them.

---

## ADR-009 — Provider plugins via entry points; config binds by name

**Status:** Accepted · 2026-07-11

**Context.** Goal G5: adding a provider must require zero core changes.

**Decision.** Built-in adapters self-register in a `ProviderRegistry`; third-party adapters register through the Python entry-point group `ai_orchestrator.providers` (standard `importlib.metadata` discovery — install a package, gain a provider). Config references providers only by registry name. Prompt templates are similarly overridable per project (`.ai/prompts/<role>.md`).

**Alternatives considered.** (a) Config-declared shell command templates ("provider = any command string") — tempting zero-code extensibility, rejected as the *primary* mechanism: parsing, health checks, and capability flags need code. A generic `shell` adapter may still ship later for quick experiments. (b) Plugin directory scanning (`~/.ai/plugins/*.py`) — rejected: imports arbitrary unpackaged code; entry points are the packaging-native standard.

**Trade-offs.** Writing a plugin requires making a (tiny) Python package. Acceptable for the target audience.

**Future implications.** Roles and even pipeline definitions could later use the same pattern (custom pipelines as plugins) without core changes.

---

## ADR-010 — Prompts delivered via stdin, never argv

**Status:** Accepted · 2026-07-11

**Context.** Rendered prompts are multi-kilobyte, multi-line, quote-riddled strings containing user text and file paths.

**Decision.** Transport passes the prompt on stdin (all three CLIs accept it); argv carries only flags. No shell interpolation anywhere — `subprocess` with an argv list, `shell=False`.

**Alternatives considered.** Argv-embedded prompts — rejected: shell-escaping bugs, ARG_MAX limits, prompts leaking into `ps` output. Temp-file + `@file` flags — unnecessary given stdin works.

**Trade-offs.** None material. Debugging remains easy because every rendered prompt is persisted in `prompts/` anyway.

**Future implications.** Also the right shape for future streaming input.

---

## ADR-011 — Stack: Python 3.12 + uv + Typer + Rich + pydantic + YAML

**Status:** Accepted · 2026-07-11

**Context.** Spec-mandated: Python 3.12+, uv, Typer, Rich, YAML, macOS-first. This ADR records the confirmation and the deliberate additions/exclusions.

**Decision.** As specified, plus **pydantic** for config/result validation (typed config with actionable load-time errors) and **pytest** for testing. Explicitly excluded from MVP: any LLM SDK (no `openai`/`anthropic` packages — providers are CLIs, per ADR-003), any async framework (sequential pipeline; `subprocess.run` suffices), any agent framework.

**Alternatives considered.** Click vs Typer (Typer = Click + type hints; fine), dataclasses + manual validation vs pydantic (pydantic wins on error messages for user-authored YAML), asyncio (rejected: no concurrency exists in the MVP to justify it — see IMPLEMENTATION_PLAN.md non-goals).

**Trade-offs.** pydantic is a heavyweight dependency for config alone, but it also types `run.json` and adapter results.

**Future implications.** If parallelism ever lands (post-MVP roadmap §4.7), the sequential engine loop is the only component that changes; nothing in the stack blocks it.

---

## ADR-012 — Antigravity CLI replaces Gemini CLI as the Designer provider

**Status:** Accepted · 2026-07-11 · **Confirmed with the project owner. Amends ADR references to "Gemini CLI" throughout the doc set.**

**Context.** Google shut down Gemini CLI for personal Google accounts on 2026-06-18 ("This client is no longer supported for Gemini Code Assist for individuals"), directing individuals to the Antigravity product family. Discovered during provider authentication for M1. Gemini CLI remains usable only with enterprise subscriptions or paid API keys.

**Decision.** The Designer role's provider becomes the **Antigravity CLI** (`agy`) — provider name `antigravity`, command `agy`, headless invocation `agy -p` (with explicit approval policy flags for non-interactive use). Task T12 builds `providers/antigravity.py` instead of `providers/gemini.py`. The underlying models are still Google's Gemini family, so the Designer role's purpose is unchanged.

**Alternatives considered.** (a) Paid Gemini API key with the old CLI — works today but adds per-token billing and rides a deprecated client. (b) Defer the Designer role entirely — zero cost and the stage is off by default, but the project owner chose to keep three live providers.

**Trade-offs.** `agy` is young: flag stability and structured-output support are unverified until T12's fixture capture; token usage may be unreportable (already tolerated by the adapter contract — `Usage = None`). Install is a curl-pipe shell script rather than a package manager.

**Future implications.** This is the provider-agnosticism goal (G5) exercised for real, before the adapter layer even exists: the change touched one config default and zero core design. If `agy` proves unstable, swapping back to `gemini` + API key is a config edit plus one adapter.
