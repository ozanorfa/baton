# Implementation Plan — AI Coding Orchestrator

**Status:** Frozen snapshot of the build plan · milestones complete 2026-07-12 · §4's post-MVP roadmap is kept current; everything else is history — what shipped since is in [CHANGELOG.md](../CHANGELOG.md), [DECISIONS.md](DECISIONS.md) and [WORKLOG.md](WORKLOG.md) · progress detail in [TASKS.md](TASKS.md), history in [WORKLOG.md](WORKLOG.md)
**Related docs:** [ARCHITECTURE.md](ARCHITECTURE.md) · [DECISIONS.md](DECISIONS.md) · [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) · [TASKS.md](TASKS.md) · [MVP.md](MVP.md)

---

## 1. Project Vision

A **local-first AI Coding Orchestrator** that turns multiple AI coding CLIs (Claude Code, Codex CLI, Antigravity CLI) into a single deterministic development pipeline, driven by one command:

```bash
batonai "Add Face ID support to the Flutter application"
```

The developer never copies a prompt between tools again. The orchestrator routes each stage of the work to the assistant best suited for it, forwards outputs between stages automatically, preserves every artifact on disk, and produces an execution report — all coordinated by plain Python code, never by another LLM.

**This is not an agent framework.** There is no supervisor agent, no dynamic delegation, no emergent behavior. Orchestration logic is deterministic code; the AI tools are treated as specialized, replaceable workers.

### Guiding principle

> Coordination should cost zero tokens. Models are spent only on the work itself — planning, designing, coding, reviewing — never on deciding who does what.

---

## 2. Goals

| # | Goal | Success signal |
|---|------|----------------|
| G1 | Eliminate manual prompt copying between AI tools | Full pipeline runs from a single command with no clipboard use |
| G2 | Route work to the best-suited AI per role | Role→provider bindings in config; each stage runs on its configured provider |
| G3 | Reduce token usage | Stages receive minimal layered context; no coordination tokens; report shows per-stage usage |
| G4 | Single CLI for development tasks | `batonai <request>` plus a small set of subcommands (`batonai runs`, `batonai config`, …) |
| G5 | Provider-agnostic | Adding a new AI CLI requires only a new adapter + config entry — zero core changes |
| G6 | Modular, maintainable, extensible | Clean layer boundaries (CLI → engine → adapters → transport); every layer independently testable |

## 3. Non-Goals

Explicitly out of scope — some permanently, some for the MVP phase:

**Permanent non-goals**
- Building a general-purpose agent framework (LangChain/CrewAI competitor).
- LLM-driven orchestration decisions (a "supervisor agent"). Routing is code.
- A hosted/web product. This is a local developer tool.
- Replacing the underlying CLIs' own capabilities (we orchestrate them, we don't reimplement them).

**MVP-phase non-goals** (revisited post-MVP, see §7)
- Parallel stage execution.
- Automatic retries or provider escalation/fallback.
- Dynamic pipeline reordering.
- tmux-based interactive sessions (headless-first transport was chosen; see DECISIONS.md ADR-002).
- Additional roles: Tester, Documentation, Security, Performance, Deployment.
- MCP server integration and long-term memory.
- Cross-run learning or prompt auto-optimization.

---

## 4. Milestones & Roadmap

Each milestone ends in a demonstrable, working state. One milestone at a time; no milestone starts until the previous one is reviewed.

### M0 — Foundations *(docs → skeleton)* ✅ 2026-07-11
Project scaffolding: `uv` project, package layout, Typer entry point, logging setup, config loading (user + project YAML merge), run-directory management (`.ai/runs/<run-id>/`).
**Demo:** `batonai --version`, `batonai config show` prints the merged effective config.

### M1 — Provider Adapter Layer ✅ 2026-07-11
`ProviderAdapter` ABC + the headless subprocess transport. Three concrete adapters: Claude Code (`claude -p --output-format json`), Codex CLI (`codex exec`), Antigravity CLI (`agy -p`, ADR-012). Health checks (binary present, authenticated), output parsing, token-usage extraction where available.
**Demo:** `batonai doctor` verifies all three CLIs; `batonai ask --role coder "hello"` round-trips a single prompt through one provider.

### M2 — Pipeline Engine ✅ 2026-07-11
Deterministic stage runner: reads the stage list from config, executes stages sequentially, passes each stage the previous stage's artifact, writes all artifacts to the run directory, fail-stop semantics (log, preserve outputs, halt).
**Demo:** a two-stage pipeline (Planner → Coder) runs end-to-end on a toy request.

### M3 — Context Management ✅ 2026-07-11
Layered context assembly (Global / Project / Task / Agent), role prompt templates, minimal-context rule enforced in one place. Project context bootstrap (`batonai init` generates a project profile).
**Demo:** stage prompts visible in the run directory show each role received only its layer-appropriate context.

### M4 — MVP: Full Four-Role Pipeline ✅ 2026-07-12
Planner → Designer (optional, config/flag-gated) → Coder → Reviewer wired together; execution report (JSON + Rich terminal summary): duration, provider, status, artifacts, token estimates. This is the MVP defined in [MVP.md](MVP.md).
**Demo:** `batonai "Add Face ID support to the Flutter application"` completes all stages and prints a report.

### M5 — Hardening & DX polish ✅ 2026-07-12
Failure-path UX (clear resume instructions after fail-stop), `batonai runs list/show`, run resumption from a failed stage (`batonai resume <run-id>`), timeouts, structured logs, test coverage across engine + adapters.
**Demo:** kill a provider mid-run → clean failure report → `batonai resume` continues from the failed stage.

### Post-MVP roadmap (ordered, not scheduled)
1. ~~**Session persistence**~~ — **shipped 2026-07-12 as ADR-015** (same-provider chaining within a run; live-verified cached-token ratio rising 70%→84% through the chain). Cross-run session reuse (resuming a project's *last* run) remains open for the future memory system.
2. **tmux observability layer** — optional live view of provider processes (borrowing CAO's patterns); never the parsing mechanism.
3. **New roles** — ~~Tester first~~ **shipped 2026-07-27 as ADR-024** (zero-LLM `testrunner`, `--with-tester`); the Publisher followed as ADR-014/017/018. Still open: Documentation, Security, Performance, Deployment.
4. **Retries & escalation** — policy-driven (config), still deterministic.
5. **MCP integration** — expose the orchestrator as an MCP server so other tools can invoke pipelines; consume MCP tools for context enrichment.
6. **Memory system** — per-project persistent knowledge (decisions made, conventions learned) fed into the Project context layer.
7. **Parallelism** — only where the DAG genuinely allows it (e.g., independent review dimensions).

---

## 5. MVP Scope (summary — full detail in MVP.md)

**In:** one command → four-stage deterministic pipeline → disk artifacts → execution report. Three provider adapters (Claude Code, Codex CLI, Antigravity CLI), headless transport, YAML config with role→provider bindings, layered context, fail-stop error handling, run history on disk.

**Out:** everything listed under MVP-phase non-goals (§3).

**MVP acceptance test:**
```bash
cd my-flutter-app
batonai init
batonai "Add Face ID support to the Flutter application"
# → plan.md, design.md, code changes, review.md, report.json in .ai/runs/<run-id>/
# → terminal summary: stages, providers, durations, token estimates, verdict
```

---

## 6. Technical Risks

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|-----------|--------|------------|
| R1 | **CLI flag/output-format drift** — vendors change headless flags or JSON schemas | High | Medium | Isolate all CLI specifics inside adapters; version-pin known-good invocations; `batonai doctor` detects breakage early; adapter contract tests with recorded fixtures |
| R2 | **Codex/Antigravity headless output less structured than Claude's** — token counts or clean result extraction may be unavailable | Medium | Medium | Adapter contract makes token usage *optional* (`None` = unavailable); report marks estimates vs. measured |
| R3 | **Coder stage needs write access & interactivity** — Claude Code headless may pause on permission prompts | Medium | High | Run Coder with explicit permission flags (e.g. `--permission-mode acceptEdits` scoped to the project dir); document the trust model; fail-stop if the CLI blocks on input |
| R4 | **Context bloat defeats the token goal** — naive forwarding of full stage outputs grows context each stage | Medium | High | Layered context with per-stage input contracts (Coder gets the plan, not the raw planner transcript); artifact summarization hooks post-MVP |
| R5 | **Cross-provider quality variance** — a weak plan poisons downstream stages | Medium | Medium | Fail-stop + human review points; artifacts on disk make every stage inspectable; `batonai resume` allows fixing an artifact and continuing |
| R6 | **Auth/subscription entanglement** — three tools, three login states, rate limits | Medium | Low | `batonai doctor` checks auth for every configured provider before a run starts, not mid-pipeline |
| R7 | **Scope creep toward "agent framework"** | Medium | High | Non-goals list (§3) is normative; any dynamic-orchestration proposal requires an ADR in DECISIONS.md |

---

## 7. Phase Plan

| Phase | Content | Exit criterion |
|-------|---------|----------------|
| **Phase 1** (current) | Six design documents | All docs reviewed & internally consistent |
| **Phase 2** | M0–M2 implementation | Two-stage pipeline demo |
| **Phase 3** | M3–M4 implementation | MVP acceptance test passes |
| **Phase 4** | M5 hardening | Failure/resume demo passes |
| **Phase 5+** | Post-MVP roadmap items, one at a time | Per-item |
