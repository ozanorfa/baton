# Architectural Decision Records — AI Coding Orchestrator

**Status:** Living · 33 ADRs · updated 2026-07-29
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
| [ADR-013](#adr-013) | Context adapts to workspace maturity; detection is deterministic code | Accepted |
| [ADR-014](#adr-014) | Optional Publisher role: per-project, per-provider, prepare-only | Accepted |
| [ADR-015](#adr-015) | Same-provider session chaining, capability- and access-aware | Accepted |
| [ADR-016](#adr-016) | Default provider assignment spreads quota across three pools by task depth | Accepted |
| [ADR-017](#adr-017) | Publisher runs on opencode (a free-tier client), confined to shallow text | Accepted |
| [ADR-018](#adr-018) | A zero-LLM Publisher floor: conventional-commit from the diffstat | Accepted |
| [ADR-019](#adr-019) | `ai revise`: session-preserving iteration instead of a chat mode | Accepted |
| [ADR-020](#adr-020) | `ai publish`: the one deliberate, user-triggered exception to "no git" | Accepted |
| [ADR-021](#adr-021) | A declared no-op is a success, not a silent-permission-block failure | Accepted |
| [ADR-022](#adr-022) | `ai review`: the Reviewer on demand, over the current diff | Accepted |
| [ADR-023](#adr-023) | A bounded fix-loop: one automatic pass on a NEEDS WORK verdict | Accepted |
| [ADR-024](#adr-024) | A zero-LLM Tester role: run the project's tests, report the result | Accepted |
| [ADR-025](#adr-025) | Optional repowise code-health context: hotspots in every stage prompt | Accepted |
| [ADR-026](#adr-026) | `batonai`: an interactive front door (scan → offer → run) | Accepted |
| [ADR-027](#adr-027) | Baton's own footprint is never mistaken for the coder's work | Accepted |
| [ADR-028](#adr-028) | Code-health is computed once per project and cached in `.ai/`, not per run | Accepted |
| [ADR-029](#adr-029) | A repository with no baseline commit is reported, never fixed by baton | Accepted |
| [ADR-030](#adr-030) | Live progress notes from the provider's own event stream | Accepted |
| [ADR-031](#adr-031) | Model choice is asked at setup and pinned per project | Accepted |
| [ADR-032](#adr-032) | `batonai setup`: the routing and model decisions stay revisable | Accepted |
| [ADR-033](#adr-033) | Model suggestions are shared and live-discovered, not silently absent | Accepted |
| [ADR-034](#adr-034) | Hardening pass: no silent states — crashes recorded, trees compared to a baseline, process trees killed, opt-in command access | Accepted |

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

**Amendment (2026-07-11, during T12).** Antigravity CLI 1.1.1 cannot read prompts from stdin (`-` is taken as a literal prompt). Exception granted: providers without stdin support pass the prompt as a single argv element. The original risks stay controlled — `shell=False` everywhere means no interpolation regardless, ARG_MAX (~256 KB on macOS) far exceeds any stage prompt, and `ps`-visibility is acceptable for a local tool. Stdin remains mandatory for providers that support it.

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

---

## ADR-013 — Context adapts to workspace maturity; detection is deterministic code

**Status:** Accepted · 2026-07-12 · **Code-reviewed and approved by the project owner.**

**Context.** Established projects and greenfield directories need different context: an existing codebase has documentation and conventions the stages should read and respect; an empty directory has nothing to read, and stages must instead propose structure explicitly. Requested by the project owner ("read the MD files of existing projects before continuing; for a new project it is not a requirement").

**Decision.** A pure-code detector classifies the workspace as **established** or **greenfield** (by counting real source files, excluding tool/VCS directories). The classification changes only the *context layers*, never routing (ADR-004 intact):

- **Established:** the Project layer gains (a) a capped repo map (file tree) for orientation, (b) a docs index — paths + titles of README/docs/*.md/CONTRIBUTING/ARCHITECTURE — plus a short capped README excerpt, and (c) an explicit instruction to *read the indexed documents with the agent's own tools*. Full documents are never inlined (minimal-context principle, risk R4): we point agents at doors, we don't carry the furniture.
- **Greenfield:** none of the above; instead a short note telling stages to propose structure/stack explicitly and state assumptions loudly. The CLI additionally suggests `git init` when absent, since diff capture and silent-failure detection depend on git.

**Alternatives considered.** (a) Inline full doc contents — rejected: unbounded token cost on every stage of every run. (b) LLM classifies the workspace — rejected per ADR-004. (c) `ai init --generate` (AI-written profile) — deferred: the docs index may make it redundant; measure first.

**Trade-offs.** Heuristic detection can misclassify exotic layouts (override-able via config later if it ever matters). The docs index costs a few hundred tokens per stage — accepted, it replaces thousands of exploration tokens.

**Future implications.** The workspace layer is the natural mount point for the future memory system (ADR/roadmap) and repo-map improvements (symbol maps).

---

## ADR-014 — Optional Publisher role: per-project, per-provider, prepare-only

**Status:** Accepted · 2026-07-12 · **Confirmed with the project owner.**

> **Standing guarantee, restated for anyone skimming:** this role is **disabled by default in every project** and cannot be enabled by accident — only an explicit `--with-publisher` flag or an explicit `roles.publisher.enabled: true` line in that project's own `.ai/config.yaml` turns it on. Even then, it **never runs `git commit`, `git push`, `gh pr create`, or any other state-changing command** — its only capability is writing a markdown draft into the run's artifact folder. Verified live on a real repository (`git log` before/after a `--with-publisher` run showed zero new commits) before this ADR was accepted.

**Context.** The project owner asked how the orchestrator decides *which provider* handles git/publish-type actions, and whether some projects should have that capability while others don't — using GitHub push as the illustrative case but asking for a general answer ("think more wisely"). Evaluated whether Amazon CAO's dynamic supervisor-routing model would serve this better.

**Decision.** Reject dynamic routing again (consistent with ADR-001/ADR-004) and instead add **Publisher** as a fifth optional built-in role, following the exact pattern of Designer:

- Off by default; a project opts in via `pipeline.stages` and picks its own provider (`roles.publisher.provider`), independent of the Coder's provider — e.g. Codex prepares the commit even though Claude wrote the code.
- **Prepare-only** (per explicit user decision): the stage drafts `commit_message.md` and `pr_description.md` as artifacts. It never runs `git commit`, `git push`, or `gh pr create`. The human executes those, same as ADR-007's Coder boundary.
- Runs read-only (no `allow_edits`), same sandbox class as Planner/Reviewer.
- Its contract input is the Reviewer's verdict + the diff — it only drafts a publish narrative for work that's already been reviewed.

**Why this beats CAO's dynamic model for this exact request.** The ask was "guarantee Codex handles this, never Claude, per project." A supervisor-LLM router can't offer that guarantee — it decides fresh, at runtime, per call, at token cost. A static per-project config entry offers it absolutely, for free, and is auditable by reading a YAML file before any run happens.

**Alternatives considered.** (a) Auto-commit — rejected per user decision, escalates the trust model without a clear win. (b) Auto-commit-and-push — rejected, same reasoning, larger blast radius (touches the remote). (c) Fold this into the Reviewer's job — rejected: violates single-responsibility (spec §5); reviewing and drafting a release narrative are different jobs and may legitimately want different providers.

**Trade-offs.** One more optional stage most projects will leave disabled; the artifacts are extra files to generate/read. Accepted — opt-in cost only.

**Future implications.** If real usage later asks for actual commit/push automation, that is a *new, separate* ADR and an explicit trust-model escalation — never a silent capability creep on this one. The same per-project/per-provider pattern generalizes to any future optional role (Tester, Deployment, …).

---

## ADR-015 — Same-provider session chaining, capability- and access-aware

**Status:** Accepted · 2026-07-12 · **Live-verified on real infrastructure.**

**Context.** The project's founding goal is token efficiency through division of labor, but the actual mechanism for it (roadmap #1, "session persistence") had never been built: every stage cold-started, even when consecutive stages happened to share a provider (by default, Planner/Reviewer/Publisher are all Codex). The project owner directly challenged this gap after reviewing real run costs. A proposal to instead route the *entire* pipeline through one provider was raised and correctly rejected by the owner: "if we use only one provider, why use the orchestrator at all? I could type into Codex CLI directly." That objection is decisive — the value of this tool is routing different work to *different, specialized* models (proven by the stopwatch run, where Codex caught a real bug in Claude's own code); collapsing to one vendor for cost reasons would destroy the thing worth having. Session chaining is the alternative that gets the token benefit without touching which model does which job.

**Decision.** Track a session id per **provider name** (not per stage) as the pipeline runs. When a stage's provider already has an open session from an earlier stage, resume it instead of cold-starting — regardless of how many stages of a *different* provider ran in between (Planner→Coder→Reviewer still chains Reviewer to Planner, skipping over Coder's unrelated Claude session). Never crosses providers — Codex cannot resume a Claude session or vice versa; that is a hard vendor boundary, not a policy choice.

Two safety conditions gate every chain, both discovered as real bugs during live verification before this ADR was written:

1. **`adapter.capabilities.supports_resume` must be true.** Antigravity is excluded outright (§3.3 of ARCHITECTURE.md — its `-p` mode never reports a session id).
2. **The prior session's `allow_edits` must match the current stage's.** Live testing found `codex exec resume` **rejects `-s/--sandbox` outright** ("error: unexpected argument '-s' found") — a resumed session keeps the write-access level it was created with. Chaining a read-only stage's session into an edit-needing stage would silently leave it unable to write (or worse, silently keep old access), so the engine refuses to chain across an access-level boundary. In the default pipeline this is moot (Planner/Reviewer/Publisher are all read-only), but the guard makes the feature correct for any project that reassigns Coder to a chaining-eligible provider too.

Per-project escape hatch: `pipeline: {session_chaining: false}` restores full stage independence.

**The ADR-006 tension, named honestly.** ADR-006 says stages hand off artifacts, not transcripts. Session chaining is a deliberate, bounded exception to that rule for *same-provider* stages only: a resumed session's model literally retains its own prior turns. This never leaks cross-vendor (Claude still never sees Codex's reasoning or vice versa — the cross-model check that catches bugs is untouched), and role boundaries are still enforced by each stage's prompt instructions, not by context isolation. The trade-off is a minor loss of Reviewer independence *from the Planner specifically* (both being Codex) in exchange for real, measured token savings — judged acceptable and made opt-outable.

**Live verification (2026-07-12, real Codex CLI, `--with-publisher` run).** `run.json` showed the identical Codex session id across Planner, Reviewer, and Publisher — proof it is one continued conversation, not three. Cached-token ratio *rose* through the chain (Planner 70% cached → Reviewer 83% → Publisher 84%), meaning each stage's fresh, full-price token cost stayed roughly flat (~15–17k) instead of re-paying for repo exploration from zero each time.

**Alternatives considered.** (a) Single-provider "cheap mode" (route every role through one vendor) — rejected per the project owner's objection above; it forfeits the tool's entire reason to exist. (b) A live, back-and-forth clarification protocol between stages (Coder asks Codex a question mid-task, gets an answer, resumes) — evaluated as a separate idea in the same conversation and set aside: every round trip is a fresh invocation, cross-provider rounds have zero session to resume, and it reintroduces the runtime-routing-decision problem ADR-001/004 already rejected. Left for a future, narrowly-scoped ADR if plan-quality gaps ever justify the extra cost.

**Trade-offs.** Slight loss of Reviewer independence from the Planner (same continued Codex mind). Two real CLI-compatibility bugs surfaced and were fixed as part of accepting this ADR (see below) rather than left as latent landmines.

**Future implications.** The `provider_sessions` map is the natural extension point for cross-run memory (if a future memory system wants to resume the *last run's* final session for a project instead of always starting cold on run 1).

### Bugs found and fixed while verifying this ADR

1. **`codex exec resume` rejects `-s/--sandbox`.** `CodexAdapter.build_invocation` now omits the sandbox flag whenever resuming (see `providers/codex.py`).
2. **Naive chaining could silently strand a stage at the wrong access level.** Fixed via the `allow_edits`-matching guard described above, with a dedicated regression test (`test_mismatched_allow_edits_never_chains`).

---

## ADR-016 — Default provider assignment spreads quota across three pools by task depth

**Status:** Accepted · 2026-07-12 · **Confirmed with the project owner.**

**Context.** The project owner clarified a real goal after ADR-015 shipped: not a *reduction* in total tokens spent, but a *spread* of the same total across independent subscription pools, so no single one (as happened once with Claude's session limit) gets exhausted alone. Illustrated as: "it was once 10,000 tokens by Claude Code, presume — now 4,000 codex, 5,000 claude, 1,000 antigravity — same total, but separated. This is OK, they're all 10,000 in total."

**Decision.** Change the shipped defaults so the three providers split the pipeline by *task depth*, not arbitrarily:

- **Codex holds the deep, chained pair: Planner + Reviewer.** These two genuinely benefit from ADR-015's session chaining — Reviewer needs the Planner's accumulated understanding of the repo, not just its output artifact.
- **Claude holds Coder, alone, always.** Unchanged — the one role where model choice is load-bearing (its own quota pool, its own session, per ADR-007's trust model).
- **Antigravity holds the two shallow, bounded jobs: Designer + Publisher.** Neither benefits much from chaining anyway (each is a single-purpose, bounded task — sketch a UI, draft a commit message), so losing cross-vendor chaining costs little, while moving them off Codex's pool entirely frees that pool for the deep work.

Publisher's default provider changes from `codex` to `antigravity` (Designer was already `antigravity`). Both remain independently overridable per project — ADR-014's "independent of the coder's provider by design" now reads more precisely as "independent of every other role's provider."

**Trade-offs, stated plainly.**
1. **Publisher loses session chaining** (ADR-015 only ever applied within a provider) — it becomes a cold Antigravity call instead of a cheap, ~84%-cached continuation of Reviewer's Codex session. In raw token terms this is a wash or slightly worse; the point is which *pool* pays, not the total.
2. **Publisher loses token/cost visibility.** Antigravity's `-p` mode reports no usage data at all (already true and accepted for Designer). `ai runs show` will display `—` for Publisher's tokens even though real work happened.

Both are accepted explicitly: the goal is quota-pool diversity, not per-stage cost minimization, and the owner confirmed this trade-off in advance.

**Alternatives considered.** (a) Leave Publisher on Codex, document Antigravity as an opt-in recipe only — rejected: the owner's stated preference is for the spread to be the default experience, not something every project has to opt into by hand. (b) Spread Reviewer to Antigravity instead of Publisher — rejected: Reviewer benefits materially from chaining with the Planner (shared repo understanding); Publisher does not, making it the correct one to move.

**Future implications.** If a fourth provider is ever added, the same principle applies: assign it to whichever role is shallowest/most bounded, keeping the chained Planner→Reviewer pair together and Coder untouched, unless real usage shows otherwise.

---

## ADR-017 — Publisher runs on opencode (a free-tier client), confined to shallow text

**Status:** Accepted · 2026-07-21 · **Confirmed with the project owner.**

**Context.** ADR-016 spread quota across three *paid* subscription pools, but the pipeline's shallowest job — Publisher (draft a commit message + PR description from the diff), and the `ai ask --role publisher` escape hatch — still consumed a paid pool for work that plainly doesn't need a frontier model. `docs/IDEAS.md` evaluated free clients (opencode, aider) and picked opencode: `opencode run` is non-interactive and never touches git on its own, so ADR-014 holds by construction; aider was rejected (it edits code and auto-commits).

**Decision.** Add an `opencode` provider adapter (`src/ai_orchestrator/providers/opencode.py`, a near-mirror of `antigravity.py`) and change Publisher's default provider from `antigravity` to `opencode`. This takes the shallowest role off the paid pools entirely. `ai ask` inherits this automatically — it derives its provider from the named role (`--role publisher`), so no change to `ask.py` was needed.

**The load-bearing guardrail — shallow text only.** opencode is a free *client*; the model comes from a user-configured **free tier** (OpenRouter `:free`, Google AI Studio free-tier key, opencode promo models). Those tiers are rate-limited and typically **may train on submitted data**. That is acceptable for a commit message but not for proprietary source, so opencode is wired to Publisher and `ai ask` only — **never Coder or Reviewer**, which read the codebase. The model is never pinned by the orchestrator (`model: null`); the user points opencode at a backend via `opencode auth`.

**Verified against opencode 1.18.4.**
- Prompt rides in argv (variadic positional `run [message..]`), passed after a `--` separator so a dash-leading prompt is never parsed as a flag — a documented ADR-010 exception shared with antigravity. shell=False everywhere.
- Plain-text answer on stdout; stderr is log noise, ignored on exit 0. No token usage on stdout in run mode → `reports_tokens=False`, Usage stays honest-None (risk R2), matching antigravity's known blind spot.
- Session id not surfaced on stdout in default format → `supports_resume=False`.
- `--auto` (tool auto-approve) and `--share` (public session upload) are **never** passed. The roles opencode serves are `allow_edits=False` by contract, so edit permissions are never auto-approved: `edits_files=False` holds in practice, not just by declaration.

**Trade-offs, stated plainly.**
1. **Same visibility loss as ADR-016's antigravity move** — no token/cost numbers for Publisher. Already accepted for the shallow roles.
2. **Depends on the user configuring a free backend.** If none is set up, `ai doctor` still shows opencode healthy (the binary is present) but a real Publisher run fails until a model is authorized. Documented in `HOW_TO_USE.md` §7.
3. **Free-tier data-training risk** — mitigated structurally by the shallow-text-only guardrail, not just by advice.

**Alternatives considered.** (a) aider — rejected (edits code, auto-commits, fights ADR-014). (b) A local LLM / Ollama — ruled out by the owner. (c) Keep Publisher on antigravity — rejected: it still spends a subscription pool on the cheapest work, which opencode removes entirely.

**Escape hatch.** Fully overridable per project — a team uneasy about free tiers sets `roles: {publisher: {provider: codex}}` in `.ai/config.yaml` and gets the old behavior back.

---

## ADR-018 — A zero-LLM Publisher floor: conventional-commit from the diffstat

**Status:** Accepted · 2026-07-21 · *Amended by ADR-034 (2026-10-21): the floor now reads `git status --porcelain -z` instead of `git diff HEAD --stat`, so brand-new untracked files are no longer invisible to it.*

**Context.** ADR-017 moved the Publisher onto a free tier, but free tiers are rate-limited and need a configured backend. For a trivial diff, or when the free tier is throttled, even that is more than the job needs. `docs/IDEAS.md` parked a "floor": generate the commit message deterministically from the diff — no model at all.

**Decision.** Add a `deterministic` provider (`src/ai_orchestrator/providers/deterministic.py`) that produces a conventional-commit message from `git diff HEAD --stat`. It is **not** a default; select it per project: `roles: {publisher: {provider: deterministic}}`.

It honors the pure-adapter contract (ARCHITECTURE §3.1) by delegating the one side effect to the transport: `build_invocation` returns the `git diff HEAD --stat` command; `parse` transforms the resulting stat. The transform (`message_from_diffstat`) is a **pure function**, unit-tested directly on stat fixtures with no git and no subprocess — the same testability property every other adapter has.

**What it infers, and what it refuses to.** Deterministic means it never invents intent it cannot know:
- **type** — `docs` when every path is docs/`*.md`, `test` when every path is a test path, else `chore`. No `feat`/`fix` guessing.
- **scope** — the common top-level directory, but only when *all* changed files share one (a repo-root file like `README.md` collapses it to no scope, avoiding a misleading label).
- **body** — the raw `N files changed, …` summary line plus the file list.

**Trade-offs, stated plainly.**
1. **`git diff HEAD` does not see brand-new untracked files.** A frontier Publisher would. This is the explicit cost of zero-LLM; documented in the module docstring. (Verified live: a run over this session's working tree listed the 6 tracked/modified files and omitted the untracked new adapters — expected.)
2. **The message is structural, not narrative** — it says *what* changed, not *why*. That is the definition of a floor; use ADR-017's opencode Publisher or a paid provider when the "why" matters.

**Alternatives considered.** (a) An automatic fallback — the engine catches a Publisher provider failure and retries with `deterministic`. Deferred: it needs engine retry plumbing; the per-project provider selection ships the value now with no orchestration change. (b) Parsing the diff out of the assembled prompt instead of running git — rejected as fragile; running `git diff` in the workdir is self-contained and doesn't depend on artifact plumbing.

---

## ADR-019 — `ai revise`: session-preserving iteration instead of a chat mode

**Status:** Accepted · 2026-07-21 · **Confirmed with the project owner.**

**Context.** The owner wanted baton to feel less like a one-shot relay and more conversational — "make a correction, don't start over, then say push it." A full interactive `ai chat` mode was **rejected**: it would rebuild Claude Code (weakly) on top of the CLIs, require a coordinating supervisor layer (spending tokens on coordination, against ADR-001), and dissolve baton's deterministic identity and its one differentiator (multi-model relay + quota spread). The insight instead: **the conversational layer already exists — it is Claude Code driving baton**; what was missing was iterating on a run without a cold restart. This is also the manual cousin of the still-parked "fix-loop" idea, and a direct answer to the "handoff, not a team" reflection in the worklog (2026-07-13).

**Decision.** Add `ai revise "<correction>"`. It takes the last run (or `--run <id>`), re-runs from the **Coder by default** (`--from <stage>` overrides, e.g. `planner`), keeps the same run-id, and reuses on-disk artifacts. Two mechanisms make it feel like a continued conversation rather than a redo:

1. **The Coder resumes its own prior session.** A new `PipelineEngine.revise` captures every succeeded stage's `session_id` *before* the tail reset and passes them to `_run` via a new `carry_sessions` seed. Because Claude Code's adapter is `supports_resume=True` (claude.py), the re-run Coder resumes its own Claude session and treats the correction as the next turn — it remembers what it did. Same-provider chaining still holds for the rest (the Reviewer re-chains to the Planner's Codex session). The existing `allow_edits`-matching guard (ADR-015) is unchanged, so a carried session is only reused when write-access levels match.
2. **The correction reaches every re-run stage via the request layer.** `state.request` (not frozen) is appended with the correction. This matters because the Coder's contract does *not* admit `review.md` (contracts.py) — the request layer is the one channel that reliably reaches it.

**Trade-offs.** (a) Corrections accumulate in `state.request` across successive `revise` calls — deliberate (full history), at the cost of a growing request string. (b) `revise` targets a *completed* run from the Coder; a genuinely failed run is still `ai resume`'s job (resume continues from the failed stage). (c) The default reruns Coder→Reviewer, not the Planner — a plan-level correction needs `--from planner`.

**Alternatives considered.** Full `ai chat` (rejected, above). A brand-new run per correction (rejected — loses the Coder's session memory and the "don't start over" goal). Extending `resume` with a correction param (rejected — resume's semantics are "continue a failed run from where it stopped"; overloading it would blur two distinct operations).

---

## ADR-020 — `ai publish`: the one deliberate, user-triggered exception to "no git"

**Status:** Accepted · 2026-07-21 · **Confirmed with the project owner.**

**Context.** ADR-014 guarantees **no pipeline role ever runs git** — the Publisher only *drafts*. But the owner's workflow ends with "development done, now commit and push," and they were explicit they do **not** want git actions happening automatically at any pipeline stage. So the git write belongs in a separate, explicitly-invoked command — never in a role.

**Decision.** Add `ai publish`. Without a flag it **only previews** the drafted commit message (never touches git). `--commit` runs `git add -A && git commit`; `--push` also `git push`. The write is guarded and confirmed:

- **Message source precedence:** `-m` verbatim > the latest run's `commit_message.md` (if present) > a fresh draft. The fresh draft invokes the Publisher role's configured provider (opencode by default) and **falls back to the `deterministic` floor** (ADR-018) if that provider is unavailable or fails.
- **What is committed:** `git add -A` (everything — new and modified), matching "commit my work." The full file list is shown and a `typer.confirm` is required first (`--yes` skips it).
- **The only git-writing code in the project.** It mirrors the read-only guarded-`subprocess.run` idiom already used by `run.py`'s dirty-tree check; every failure mode (not a repo, nothing to commit, commit/push failure) is surfaced, never raised.

**Why ADR-014 stays intact.** The drafting (LLM/deterministic) and the git write are separate steps, and the write lives in a *user-invoked command*, not a pipeline stage. No role gained git access; a human explicitly asks for the commit each time.

**Trade-offs.** (a) `git add -A` can stage unrelated working-tree changes — mitigated by showing the file list before the confirmation (the owner chose this over "tracked-only" or "no auto-stage"). (b) Reusing the latest run's `commit_message.md` can be stale if the tree changed since that run — mitigated because the draft is always shown before committing and `-m` overrides it. (c) The commit message keeps only the commit section when the draft also embeds a "PR description" heading (a simple split, with the whole text as fallback). (d) A chatty free-tier model (observed live with opencode: "Let me check the working tree." before the real message) can prepend preamble; the fresh draft is cleaned by anchoring on the first Conventional-Commits subject line (`_strip_preamble`), and left unchanged if no such line is found — so it never mangles a message it can't parse.

**Alternatives considered.** Letting the Publisher role commit when enabled (rejected — breaks ADR-014 and the owner's "no automatic git" requirement). `--push` without confirmation (rejected — the owner is git-cautious; confirmation is the default, `--yes` opts out).

---

## ADR-021 — A declared no-op is a success, not a silent-permission-block failure

**Status:** Accepted · 2026-07-21

**Context.** ADR-007's safety net: because a permission-blocked headless run reports success at the protocol level (claude.py `permission_block.json`), the engine treats an edit-stage that returns success **but changes nothing** as a failure — the workspace is the only honest witness. This correctly catches silent blocks, but it also mislabels a **legitimate no-op**: "add a license header if missing" when the header is already there is a real, correct outcome with zero changes, yet it was failing the run.

**Decision.** Distinguish the two with an explicit, low-ceremony signal. The Coder template (`prompts/coder.md`) instructs: if no change is genuinely needed, make no edits and put exactly `CHANGE_STATUS: no_changes_needed` as the first line of the summary. The engine (`core/engine.py`), on zero workspace change, checks `result.text` for that marker (`NO_CHANGES_MARKER`): present → the stage **succeeds** with an empty diff and a `stage_no_changes` event; absent → the existing failure fires unchanged.

**Why it's safe — no regression is possible.** Absent marker + zero change behaves **exactly as today** (failure), so the permission-block detection is fully preserved. The marker only ever *relaxes a false negative*. If the model forgets to emit it on a true no-op, the result is the current behavior (a false failure) — never a false success. So a silent permission block can never be mistaken for a no-op: the block produces no marker.

**Trade-offs.** (a) The marker is a prompt convention, so it shares the fragility of any model-emitted token — mitigated entirely by the fail-safe direction (forgetting it fails safe). (b) A downstream stage (Reviewer) then sees no `diff.patch`; the contract admits it but `inputs_section` simply omits an absent artifact, so the Reviewer reviews the "nothing changed" situation cleanly.

**Alternatives considered.** (a) A structured `CHANGE_STATUS:` enum with `changed`/`no_changes_needed`/`blocked` (the original suggestion) — rejected as over-built: only the no-op case needs rescuing, and a `blocked` self-report can't be trusted (a blocked provider won't reliably say so). (b) Always trust protocol success and drop the workspace check — rejected: it throws away the only real permission-block detector.

---

## ADR-022 — `ai review`: the Reviewer on demand, over the current diff

**Status:** Accepted · 2026-07-21

**Context.** The Reviewer only ran as a pipeline stage. But its value — a second, different-vendor model checking a diff against intent — is useful on its own: to review your **own** hand-written changes, or to re-check a run's output with fresh eyes, without paying for a whole Planner→Coder→Reviewer pass. `ai ask --role reviewer` almost does it, but it sends a bare prompt with no diff and no reviewer context.

**Decision.** Add `ai review`. It captures the current working-tree diff and runs the Reviewer's configured provider over it, pipeline-free. It composes entirely from existing pieces — no new engine or context machinery:

- **Diff capture:** `snapshot_changes()` (`core/workspace.py`), the same read-only, untracked-inclusive git snapshot the pipeline uses. `None` → not a repo → exit 2; unchanged → "nothing to review" → exit 0.
- **Context:** `ContextManager.build()` with a synthetic reviewer `StageSpec` (`inputs=["diff.patch"]`) and `artifacts={"diff.patch": patch}`, so the real `reviewer.md` template + layers assemble exactly as in a pipeline run, with the captured diff as the one admitted input. `-m/--message` supplies an optional focus (e.g. "security").
- **Invocation:** the `ai ask` pattern — resolve the `reviewer` role's provider, build the adapter, `invoke(...)`, print the verdict + usage line.

**Boundaries.** Read-only by construction: the Reviewer contract is `allow_edits=False`, and the command persists nothing (no run dir, no artifacts) — it never commits, edits, or mutates state. It is *not* a pipeline stage, so ADR-004/008 (one deterministic relay, no dynamic delegation) are untouched.

**Trade-offs.** (a) Scope is the working tree only — reviewing a staged set or a branch-vs-branch range is deliberately out of scope for now (add a ref argument later if wanted). (b) It re-drafts the reviewer prompt from scratch each call (no session reuse); acceptable for an on-demand one-shot.

**Alternatives considered.** Overloading `ai ask` with auto-diff-capture (rejected — muddies ask's "one bare prompt to a role" contract; a named command is clearer and discoverable). A full second pipeline mode (rejected — far more than a single read-only reviewer call needs).

---

## ADR-023 — A bounded fix-loop: one automatic pass on a NEEDS WORK verdict

**Status:** Accepted · 2026-07-21 · **Confirmed with the project owner (default off, NEEDS WORK only).**

**Context.** The MVP pipeline is one pass: a `NEEDS WORK` verdict (a blocking finding) just lands in `review.md` and stops — the human decides (MVP.md, ADR-008 "no retries"). This is the gap the project circled longest: the "loop engineering" name and the "not like my dreams" reflection (worklog 2026-07-13) both pointed here, backed by real evidence — charm_website's run `2026-07-12_1140_0a83` produced a genuine, unactioned NEEDS WORK blocker. With `ai revise` shipped (ADR-019), the machinery to close the loop already exists.

**Decision.** Add an opt-in **fix-loop**: when the Reviewer returns `NEEDS WORK`, run exactly one automatic fix pass and stop. It reuses ADR-019 wholesale — the loop is "auto-`revise` once, with the review findings as the correction." Implemented in `cli/commands/run.py` after `execute()`, not in the engine, so the "deliberately boring" core (ADR-004/008) stays a linear interpreter:

- Trigger: `pipeline.fix_loop` on **and** run succeeded **and** `report.verdict == "NEEDS WORK"` (reused `reporter.py` `VERDICT_PATTERN`). `APPROVE WITH NOTES` is non-blocking by definition — never triggers.
- Action: load `review.md`, build a correction ("The reviewer returned NEEDS WORK … Address them, then stop:\n\n<findings>"), call `engine.revise(state, resolved, correction)` (re-runs from the Coder, which resumes its own session and treats the findings as the next turn; the Reviewer re-chains to verify).
- **Exactly one pass.** The second verdict is never re-checked, so it structurally cannot loop again — bounded by construction, no iteration counter needed.

**Settings (owner-confirmed).** Off by default — an extra Coder+Reviewer turn (the priciest stages) shouldn't be spent without asking. Opt in per run (`ai run --fix-loop`) or per project (`pipeline: {fix_loop: true}`). Triggers on `NEEDS WORK` only.

**Trade-offs.** (a) Amends ADR-008/MVP's "no retries, no loop-back" — deliberately, and narrowly (one bounded pass, opt-in). (b) With the Publisher enabled, the fix pass re-runs from the Coder, so the Publisher re-drafts against the fixed code; the pre-fix draft is superseded (minor waste, Publisher is off by default). (c) Exit code is unchanged — a NEEDS WORK run's status is still SUCCEEDED (the verdict is content, not a stage failure), so the final verdict is shown in the summary, not encoded in the exit code.

**Alternatives considered.** (a) Loop until clean / N iterations — rejected: unbounded token risk and against the owner's cost-consciousness; one pass catches the common "close but blocked" case. (b) Trigger on any non-`APPROVE` (incl. `APPROVE WITH NOTES`) — rejected: notes are explicitly non-blocking, so a fix turn there usually wastes the priciest stages. (c) Implement in the engine — rejected: it would make the linear core conditional; the CLI-level reuse of `revise` keeps the engine pure and applies the loop only to fresh `ai run` (not `resume`/`revise`, where the user already iterates by hand).

---

## ADR-024 — A zero-LLM Tester role: run the project's tests, report the result

**Status:** Accepted · 2026-07-21 · **Confirmed with the project owner (auto-detect + override, report-and-continue).**

**Context.** The pipeline had no ground truth — the Reviewer *reads* the diff and may run a check, but nothing deterministically runs the project's own test suite. Adding a Tester is the roadmap's "new role" done under the project's discipline: **add a role only when it earns its keep.** Running tests earns it — running them is deterministic (**zero tokens**), and the signal is real: broken code shows before the Reviewer even looks.

**Decision.** Add an optional `tester` role, off by default, positioned `Coder → Tester → Reviewer`, backed by a new zero-LLM `testrunner` provider (`providers/testrunner.py`, modeled on ADR-018's `deterministic`). It ignores the prompt and delegates to the transport, running the project's test command in the workdir.

- **Test command (owner choice: auto-detect + override).** `providers.testrunner.command: auto` detects from stack markers (`pyproject.toml`→`pytest`, `package.json`→`npm test`, `go.mod`→`go test ./...`, `Cargo.toml`→`cargo test`, `pubspec.yaml`→`flutter test`, …); an explicit `command` overrides. Undetectable + unset → the stage fails with a clear "set `providers.testrunner.command`" message (a config error, distinct from a test failure).
- **Report-and-continue (owner choice).** Running the tests and getting failures is still a *successful test run*, so a FAILED result is a **successful stage** whose `test_report.md` says FAILED. The Reviewer's contract gains `test_report.md` as an input, so the verdict reflects the tests — a failure → `NEEDS WORK` → (with `--fix-loop`, ADR-023) an automatic fix. Only a missing command or a timeout fails the stage itself. This composes the Tester, Reviewer, and fix-loop into one signal chain rather than a hard gate.
- Enable per run with `ai run --with-tester` (mirrored on `resume`/`revise`), or per project (`roles: {tester: {enabled: true}}`).

**Trade-offs.** (a) `testrunner`'s health check can't verify the command up front (it resolves against the run's workdir, unknown at preflight) — it returns healthy and the real check happens at run time. (b) Auto-detected commands are conventional guesses (e.g. `pytest` vs `uv run pytest`); the override exists for anything non-standard. (c) Adding `tester` to the default pipeline means an extra `○ tester skipped` row when it's off — consistent with the existing designer/publisher rows.

**Alternatives considered.** (a) Fail-stop on test failure (a gate) — rejected by the owner in favor of report-and-continue, which feeds the Reviewer/fix-loop instead of dead-ending the run. (b) Explicit-config-only (no detection) — rejected: auto-detect gives zero-config for common stacks, and the override covers the rest. (c) An LLM-backed tester that figures out how to run tests — rejected as wasteful; a deterministic command runner is cheaper and more reliable (the `tester.md` template exists only if someone deliberately binds an LLM provider to the role).

## ADR-025 — Optional repowise code-health context: hotspots in every stage prompt

**Status:** Accepted · 2026-07-27 · **Validated live before shipping** (robustness sweep + a reviewer A/B + a full end-to-end run — see WORKLOG 2026-07-27).

**Context.** The roadmap's long-parked "repowise as a context source" item (IDEAS.md item 2). The rich repowise interface is MCP-shaped and stays blocked on a future MCP client, but a **live probe (repowise 0.34.0)** established that its `health` subcommand is a clean fit for baton's existing subprocess-and-stdout provider pattern: it runs **in-process (no LLM, no network), needs no `repowise init`**, emits `--format json`, and — unlike `init` — writes nothing to machine-wide config (the `init` footgun that registered global MCP hooks in `~/.claude`, WORKLOG 2026-07-23, does **not** apply). The question this ADR answers is whether feeding that data to the models actually helps.

**Decision.** Add an optional context layer (`context/health.py`) that shells out to `repowise health --format json` and injects a bounded slice — KPI headline (file count, average health, worst performer) + the ≤5 worst-scoring files (score, cyclomatic complexity, nesting, test presence) — into the workspace section of **every** stage prompt, so the Planner plans around hotspots, the Coder avoids piling complexity onto them, and the Reviewer scrutinizes changes that touch them.

- **Opt-in, default OFF** (like the Tester and fix-loop). Enable per run with `ai run --health` or per project with `context: {health: true}`. Off by default because it adds ~4 s and needs a third-party binary.
- **Never a hard dependency, never breaks a run.** If the `repowise` binary is absent, or the call errors/times out/returns unparseable output, `health_section` returns `""` and the prompt is byte-identical to before. Established projects only (greenfield has no history to score); computed **once per run**, not per stage (it rides the `ContextManager`'s cached workspace layer).
- **Baton runs `health` itself** — no manual user setup, matching the owner's "the orchestrator should do it on its own." It **never** runs `repowise init` (machine-wide writes + token spend; a human-triggered, one-time step, always).
- **No litter.** `health` writes a ~1 MB `.repowise/` index; baton removes it **iff this call created it** — a pre-existing, user-owned `.repowise/` is never touched.
- **Bounded output, not a dump.** The raw JSON is ~25k tokens on a 113-file repo; only the fixed KPI block + top-5 worst files are injected (the rest is `WORST_FILES_MAX`-capped), so the added token cost is ~1k, measured.

**Evidence (why it ships).** A reviewer A/B on baton's own worst hotspot (`engine.py`, health 2.4/10) with a planted-bug diff, run through the real Reviewer (codex), 2× each arm: both arms caught the primary bug and returned the same verdict, but **both** health-informed runs also caught a secondary smell (`record.error = None`) that **neither** control run did — at ~1k extra tokens. A modest but consistent quality gain on the *hardest* case (a strong reviewer with full repo access); the value is a reliable nudge, not a verdict-flipper — hence opt-in.

**Amendment 2026-07-28 — the concern rule was wrong, found on a real project.** The original gate ("score < 8.0") was calibrated on baton's own repo, whose worst file scores 2.4, and did not generalize. On a Flutter project (`skii_game`) the worst file — `snow_world.dart`, **cyclomatic complexity 27**, 26% duplication, no tests — scored **8.15**, just above the cutoff, so baton injected **nothing at all**: a blended score averages a severe single dimension away. Three corrections: (1) a file is now a concern if **any** of score < 8.0, `max_ccn` ≥ 15, or `max_nesting` ≥ 4 trips, and each row states which; (2) **duplication is reported but never triggers on its own** — a constants file reads as ~100% duplicated by construction (`game_constants.dart`, score 9.7), and flagging it would evict a real hotspot from the five-slot list; (3) only **source files** are counted — repowise scores markdown, YAML and baton's own `.ai/`, which inflated the headline to "24 files analyzed · average 9.3" for a project holding 8 Dart files. Also shipped alongside: **`batonai health`**, a zero-token command that prints the exact slice, because until now the only place to read it was inside a run's `prompts/*.md` while the `.repowise/` index was deleted straight after use — an invisible feature.

**Trade-offs.** (a) Value is real but modest, and depends on repowise's static markers (complexity/nesting/dead-code), not semantic understanding — the deep repowise value remains MCP-gated and out of scope here. (b) The ~4 s + a transient `.repowise/` write are why it is off by default. (c) `health`'s numbers are only as current as the working tree at run start (a starting map, like the rest of the workspace layer — ADR-013).

**Alternatives considered.** (a) Gate on a pre-existing user-created `.repowise/` (an earlier IDEAS.md sketch) — rejected once the probe showed `health` needs no `init` and creates its own index: baton can just run it, so requiring manual user setup added friction for no benefit. (b) The full repowise MCP tool interface (`get_context`/`get_risk`/…) — still blocked on baton acquiring an MCP client (ARCHITECTURE §7.2, "Future"); a separate, larger roadmap item. (c) On by default — rejected: a third-party binary, ~4 s, and a repo write should be a deliberate opt-in, consistent with every other optional stage/feature.

## ADR-026 — `batonai`: an interactive front door (scan → offer → run)

**Status:** Accepted · 2026-07-28 · **Implemented 2026-07-28**, in the same session this ADR was written (the owner's step-by-step preference paused implementation only long enough for the design to be reviewed first). The binary rename, the wizard, and the scan/decide split described below are all live; `docs/WORKLOG.md` 2026-07-28 has the implementation and verification notes.

**Context.** Every command baton ships assumes the user already holds baton's mental model. A newcomer who opens a folder and types the command gets a Typer help dump (`no_args_is_help=True`, `cli/app.py:28`) — a list of ten subcommands with no indication of which one to type first. To get to a successful run they must already know, unprompted, to: check `doctor` before trusting anything, run `init` once per project, start from a clean git tree (the run only *warns*, after the fact), and that `--health` exists at all. `init` itself is a silent file-writer: it never asks, never reports what it found, never suggests what comes next beyond one printed line.

The owner's framing: *"son kullanıcı düşünemez kendi kendine önce gidip repowise çalıştırayım vs vs."* — the end user cannot be expected to reason their way to "first let me go run repowise." The tool knows how to inspect the workspace and knows what it needs; it should do that itself and *offer*, rather than wait to be commanded correctly.

**Decision.** Add an interactive front door, in three parts.

1. **Rename the binary `ai` → `batonai`** (`[project.scripts]`). `ai` is an unacceptably generic name for a globally-installed command; `batonai` is collision-safe and matches the project's own identity (the repo is `ozanorfa/baton`; HOW_TO_USE already titles it *"baton"*). Chosen over bare `baton` by the owner for collision-safety, accepting the extra characters.
2. **Bare `batonai` (no arguments) launches a one-shot guided wizard**: scan the workspace → report what was found → offer the missing setup → take the request → run the pipeline → exit to the shell. It is a wizard, not a REPL; a persistent `batonai>` session is a deliberate **later** step (below) built on the same scan layer.
3. **In the wizard path only, code-health runs automatically** — `repowise health` is invoked during the scan, its hotspots are *shown to the user* as part of the workspace report, and injected into the stage prompts for the run the wizard starts. This **amends ADR-025's default** (see below).

**This does not violate ADR-004, and requires no R7 exemption.** The convention line at the top of this file requires an ADR before any dynamic/LLM-driven orchestration; this is explicitly *not* that. The wizard contains **no model call and makes no judgment**: it is a fixed decision table over directly observed facts (does the directory have files, is there a `.git`, is there an `.ai/`, is a provider binary healthy, is `repowise` on PATH). It never chooses which model does which job, never reorders stages, never rewrites config — routing stays exactly what it is today: plain Python over YAML. The wizard's entire authority is *filling in setup and flags the user would otherwise have had to type*, each one shown on screen before it happens. Determinism is preserved in the sense that matters: same workspace state + same answers ⇒ same run.

**The scan → action table** (fixed, exhaustive, no inference):

| observed state | wizard action |
|---|---|
| stdin is not a TTY (pipe, CI, `\|`) | **no wizard** — print help and exit 0; scripted use is byte-identical to today |
| a provider bound to a needed role is unhealthy | print that `doctor` row and exit 2, before anything else runs |
| directory is empty | greenfield: take the request first, offer `git init` + `init`; no health scan (nothing to score) |
| non-empty, not a git repo | report that diff capture + the no-change safety net are off; offer `git init` |
| non-empty, git, no `.ai/` | *"Set up baton in this folder?"* → run `init` (stack auto-detected) → take the request |
| non-empty, git, `.ai/` present | ready: show the last run (age, request, verdict, pending changes) + a next-action menu |
| established project **and** `repowise` on PATH | run `health`, display the hotspots, inject them into the run |

**Consequences for ADR-025 (an amendment, stated plainly).** ADR-025 shipped health as *opt-in, default OFF*, on the reasoning that a third-party binary, ~4 s, and a repo write should be deliberate. That reasoning holds for **scripted** use and is unchanged: `batonai "<request>"` with an explicit request still requires `--health` or `context: {health: true}`, and without it the prompt stays byte-identical. What changes is that in the **interactive** path the deliberateness is satisfied differently — the user sees the scan happen, sees the hotspots on screen, and sees them named as input to the run. The cost ADR-025 was protecting against (a surprise dependency and a surprise 4 s) stops being a surprise when it is displayed. The fail-safe guarantees are untouched: no `repowise` on PATH ⇒ the health line is simply absent, never an error; the transient `.repowise/` is still removed iff baton created it; `repowise init` is still never run.

**Trade-offs.**
- **(a) The rename is a breaking change with a wide blast radius.** `ai` disappears; `uv tool install` must be re-run, and every occurrence across README, HOW_TO_USE, HOW_TO_USE.tr, MANUAL_TESTING, PROJECT_STRUCTURE and the test suite must move in the same commit as the code, or the docs describe a binary that does not exist. No alias is kept — a half-renamed tool with two working names is worse documentation than one clean name.
- **(b) An interactive path is a second way in, and two paths can drift.** Mitigated by construction: the wizard is a thin caller that ends by invoking the *same* `run` code path with the same config object — it holds no pipeline logic of its own.
- **(c) Prompting has failure modes a flag does not** (no TTY, Ctrl-C mid-question, a user who just hits Enter). The non-TTY row above handles the first; the wizard must treat Ctrl-C at a prompt as a clean exit 130 with nothing written, and every question must have a safe default reachable by bare Enter.
- **(d) The wizard makes the first run slower to start** (~4 s scan) in exchange for it being the *first run that succeeds*. Judged worth it for the audience this feature exists for.

**Alternatives considered.**
- **(a) Keep `ai` as an alias alongside `batonai`.** Rejected by the owner: two names means docs must either pick one (and lie about the other) or document both (and confuse newcomers about which is canonical).
- **(b) A persistent REPL now** (`batonai>` chaining run → revise → publish in one session). Deferred, not rejected — the owner explicitly chose "wizard now, REPL later." The scan/decision layer this ADR builds is the same layer a REPL would wrap, so nothing here is throwaway; the REPL adds session state and Ctrl-C semantics that deserve their own ADR.
- **(c) Auto-run health in *every* path, including scripted.** Rejected: it would impose ~4 s and a repo write on CI and on users who never asked, which is exactly what ADR-025 decided against. The wizard earns the default by being visible; a script cannot.
- **(d) Make the wizard ask a model what to do next** (e.g. "should I init here?"). Rejected on ADR-004 grounds without further discussion — every branch in the table above is answerable by looking at the filesystem, so a model call would spend tokens to learn something already known.

## ADR-027 — Baton's own footprint is never mistaken for the coder's work

**Status:** Accepted · 2026-07-28 · **Both halves found by a real end-to-end run, not by review** (WORKLOG 2026-07-28).

**Context.** The first genuine acceptance run of the ADR-026 wizard (a real project, real providers, `APPROVE WITH NOTES`) surfaced two ways the orchestrator's own leavings get attributed to the Coder:

1. **`init` edited the user's root `.gitignore`.** The wizard runs `init` and then immediately starts a run, so that edit — baton's own bookkeeping — landed in the Coder's captured diff. The live reviewer spent one of its findings on it: *"an unrelated rule ignoring `.ai/runs/` was added despite not being part of the implementation plan … adds unexplained scope."* Baton created the dirty-tree condition it otherwise warns about, and paid for it in reviewer attention.
2. **Generated artifacts reached the reviewer.** A stray `__pycache__/*.pyc` (left by a test run) was picked up by `batonai review`, which returned **NEEDS WORK** with the `.pyc` files as a *Major* finding. Git already hides *ignored* files, so this only bites where a project's `.gitignore` is incomplete — precisely the projects least able to absorb a bogus blocking verdict.

Both are the same mistake in two places: **something nobody authored is presented to a model as work someone did.** `core/workspace.py` already asserted this principle for `.ai/` ("the orchestrator's own footprint must never count as 'the coder changed something'"); it just wasn't applied consistently.

**Decision.**

- **`init` no longer touches the project's root `.gitignore`.** The ignore rule moves to **`.ai/.gitignore`** containing `runs/`. Git applies a `.gitignore` to its own directory and below, so the effect is identical — but the file lives inside the directory baton owns, and since `.ai/` is already excluded from diff capture, it can never appear in a run's diff. Verified with `git check-ignore`. Baton now edits only files it owns.
  - **Backwards compatible:** a project set up by an older baton has the rule in its root `.gitignore`; `init` detects that, leaves it alone, and does not add a duplicate. Nothing is ever removed from a user's `.gitignore`.
- **Diff capture excludes generated artifacts:** `__pycache__`, `*.pyc`, `*.pyo`, `.pytest_cache`, `.ruff_cache`, `.mypy_cache`, `node_modules`, `.DS_Store` — added to the existing `_EXCLUDE` pathspec alongside `.ai/`.
  - **Deliberately conservative.** `build/`, `dist/` and `target/` are **not** excluded: they are real source directories in some projects, and when they *are* build output they are already gitignored (so git omits them anyway). The list holds only names that are never hand-written source in any language. A test pins this: a `build/make.py` must still show up in the diff.

**Consequences.** The no-change safety net (ADR-007) gets stricter in the right direction: a stage that produces *only* generated files now correctly reads as "nothing changed" rather than passing on compiler output. That is the intended reading — a Coder whose sole effect was to populate `__pycache__` did not do the job.

**Trade-offs.** (a) A project that genuinely tracks one of the excluded names (a checked-in `node_modules`, a vendored `*.pyc`) will not see changes to it reviewed. Judged acceptable: those are rare, and the alternative — bogus Major findings and flipped verdicts — was observed in the wild on the very first real run. (b) The exclusion list is static rather than read from the project's `.gitignore`; parsing gitignore semantics correctly is a much larger job, and git already handles the ignored-file case on its own.

**Alternatives considered.** (a) Have the wizard warn the user that `init`'s files are now uncommitted — rejected: it explains a self-inflicted problem instead of removing it. (b) Exclude `.gitignore` from diff capture entirely — rejected: a user's genuine `.gitignore` edit is real, reviewable work. (c) Commit `init`'s files automatically — rejected outright; ADR-020 makes `batonai publish` the single user-invoked git command, and no other code path may commit.

## ADR-028 — Code-health is computed once per project and cached in `.ai/`, not per run

**Status:** Accepted · 2026-07-28 · **Implemented 2026-07-28** (measured: 1.96 s → 0.14 s on a repeat call).

**Context.** ADR-025 runs `repowise health` inside every run that enables it (~4 s), renders a slice into the prompts, and deletes the `.repowise/` index it created. Two costs follow. **(a)** The work is repeated for every run in a project whose code has barely moved. **(b)** The result is invisible: it survives only inside `prompts/*.md`, and the index it came from is gone — the owner's reaction on first contact was *"repowise çıktıları nerede göremedim?"*, and the honest answer was *nowhere*. `batonai health` (2026-07-28) made it printable on demand, but each invocation still recomputes.

**Decision.** Compute health **once per project** and persist the result to **`.ai/health.json`**, alongside the run history baton already owns. Later runs read the cache instead of shelling out.

- **Location.** `.ai/` — baton's own directory. It is already excluded from diff capture (ADR-027), so a cache file can never be mistaken for the Coder's work, and `.ai/.gitignore` decides whether it is committed. `.repowise/` stays transient and is still removed after use: that is *repowise's* index, not ours, and it is ~1 MB.
- **Staleness.** A cache that silently rots is worse than no cache. Refresh when the newest source file is newer than the cache, or the cache is older than a fixed age; force with `batonai health --refresh`. The stored record carries the timestamp it was produced at, and every surface that shows health states that age, so a stale reading is never presented as current.
- **Human-readable.** The file holds the rendered slice next to the raw KPIs, so opening it answers "what does baton think of this project?" with no command at all — which is the visibility half of the problem.

**Consequences.** ADR-025's "computed once per run, never cached" is superseded. The ~4 s cost moves to the first run (or to `batonai init`, which is where the owner expects it: *"işin başında tüm proje için çalışacak"*). The no-litter guarantee is unchanged in spirit — the only new file lives in the directory baton already owns.

**Trade-offs.** (a) A cache is a second source of truth and can disagree with reality; mitigated by the freshness rule and by always displaying the age. (b) `.ai/health.json` becomes something to keep valid across baton versions — it is a cache, so a format change may simply discard it rather than migrate. (c) A project edited constantly refreshes often and gains little; that is the correct behaviour, not a regression.

**Alternatives considered.** (a) Keep `.repowise/` instead of deleting it — rejected: it is a third-party ~1 MB index in the user's tree, and its lifecycle is repowise's to manage, not baton's. (b) Cache in a global directory keyed by path — rejected: invisible to the user, and the point is partly visibility. (c) Recompute per run but show it in the terminal — solves visibility only, not the repeated work.


## ADR-029 — A repository with no baseline commit is reported, never fixed by baton

**Status:** Accepted · 2026-07-28 · **Implemented 2026-07-28.**

**Context.** ADR-026's wizard offers `git init` in a non-repository. Observed on a real project (`skii_game`, 2026-07-28): the user accepted, and the run started against a repo with **zero commits**. With no `HEAD`, every file in the project reads as a change — the dirty-tree warning fires immediately and says nothing useful, `diff.patch` would be the entire project rather than the Coder's work, and ADR-007's "did anything change?" safety net loses its baseline. Baton created a state its own design assumes away.

The obvious repair — have the wizard make an initial commit right after `git init` — was **rejected**, on the owner's instruction to take whichever option is safer. ADR-020 makes `batonai publish --commit/--push` the single path by which anything reaches git history, and that guarantee is worth more than the convenience: a second committing path, however well-fenced, turns a rule a user can verify in one sentence into one with exceptions.

**Decision.** Baton continues to create **no commits, ever**, outside `batonai publish`. Instead, "git repository with no commits" becomes a **distinct, named state** rather than being folded into "uncommitted changes present":

- The wizard's scan reports it explicitly, and says what it costs — no diff capture, no meaningful change detection — instead of the current generic dirty-tree line.
- The exact command to establish a baseline is printed for the user to run. Baton does not run it.
- The `git init` offer says up front that a baseline commit is the natural next step, so the user is not led into the state blind.

**Consequences.** A user can still start a run without a baseline; baton will not stop them, and the degraded behaviour is the same as today — but it is now stated rather than discovered. ADR-020's guarantee is untouched, and stays expressible as one unconditional sentence.

**Trade-offs.** The friendlier flow (baton commits, user says yes once) stays unavailable, and some users will find the manual step tedious. Accepted deliberately: the trust model is the feature that makes an unattended Coder tolerable at all (ADR-007), and it is not worth spending for a saved keystroke.

**Alternatives considered.** (a) Auto-commit after `git init` behind a confirmation — the friendlier option, rejected above. (b) Refuse to run without a baseline — rejected as paternalistic; a user experimenting in a scratch directory has a legitimate reason not to care. (c) Stop offering `git init` at all — rejected: it removes a genuinely useful step, and the non-git state (no diff capture) is worse than the no-baseline one.


## ADR-030 — Live progress notes from the provider's own event stream

**Status:** Accepted · 2026-07-28 · **Implemented 2026-07-28 for codex; claude still buffers.** The transport, the adapter hook and the renderer are done and live-verified. `claude` keeps `--output-format json` for now: moving it to `stream-json` changes the shape its parser consumes, and that parser guards the Coder — the stage that edits files. It is a separate, testable step, and until then claude simply keeps the plain spinner, which is exactly the degradation this ADR requires of a non-streaming provider.

**Context.** A stage shows an animated spinner and nothing else for as long as it runs. Observed live: a Coder stage passed ten minutes on a Flutter project and the owner interrupted it, reasonably unable to tell *working* from *hung* — the run had not failed, and the plan behind it was genuinely large. The owner's framing: *"ara ara ufak loglar atabiliriz kullanıcıya, böylece bug olmadığını ve gerçekten çalıştığını anlar."*

**The information already exists.** Verified on a real captured log (2026-07-28): `codex --json` — the flag baton already passes — emits `thread.started`, `turn.started`, `item.started`/`item.completed` events carrying both the model's short reasoning lines and the shell commands it runs (*"I'll inspect the project documents…"*, `sed -n '200,520p' lib/src/world/snow_world.dart`). Claude Code supports `--output-format stream-json` (baton currently asks for `json`, a single blob at the end). **The only blocker is baton's own transport:** `HeadlessTransport` uses `subprocess.run`, which returns everything at once, so the stream is discarded until the stage is over.

**Decision.** Surface a bounded trickle of progress notes while a stage runs.

- **Transport gains a streaming mode** — incremental line reads instead of a single buffered call. This does not revisit ADR-002: still headless, still one subprocess, still no tmux; only the reading changes. Timeout, stdin delivery (ADR-010) and raw-log capture stay exactly as they are.
- **Adapters own the interpretation.** Each adapter may translate one raw event line into a short human note, or decline. Vendor formats stay behind the adapter boundary, as with usage parsing — a provider that streams nothing simply keeps today's spinner, and no other layer learns about it.
- **Bounded and throttled by construction.** A note is a single short line, rate-limited, and never the model's full reasoning: the goal is evidence of life and rough shape of the work, not a transcript. The complete stream keeps going to `logs/` unchanged, which stays the place to look for detail.
- **Applies to any stage that streams,** planner and coder alike (the owner asked for both: *"hem kodda hem planda"*).

**Trade-offs.** (a) Streaming is more moving parts than `subprocess.run` — partial lines, interleaved stderr, a child that dies mid-line — and the transport is a component whose simplicity is load-bearing; the streaming path must degrade to the current behaviour on any parse trouble rather than fail a stage. (b) Progress notes are vendor output rendered to the terminal: they must be treated as untrusted text (no control sequences, truncated) — a provider's output must never be able to redraw the user's screen. (c) It becomes possible to leak into the terminal something the raw log would have kept quieter; notes stay short and structural for that reason.

**Alternatives considered.** (a) A heartbeat ("still working, 4m elapsed") with no content — cheaper and safer, but it does not answer "is it doing something sensible?", which is the actual question. Kept as the fallback for providers that do not stream. (b) Parse the raw log file as it grows — avoids touching the transport, but it is the same problem solved indirectly, and the transport does not write incrementally either. (c) tmux/observability transport — the long-parked ADR-002 item; far larger, and unnecessary for this.


## ADR-031 — Model choice is asked at setup and pinned per project

**Status:** Accepted · 2026-07-28 · **Implemented 2026-07-28.**

**Context.** Baton pins no model anywhere: `providers.*.model` defaults to `null`, and the adapters pass `--model`/`-m` only when it is set. So the model in use is whatever each CLI is configured to do on its own — on the owner's machine, `codex` runs `gpt-5.6-sol` from `~/.codex/config.toml` and `claude` runs `opus` from `~/.claude/settings.json`. Neither is visible from baton, and neither was chosen for the project. The owner had to ask which models the pipeline was even using, and the answer materially explains an expensive ten-minute Coder stage.

This is a gap in a tool whose whole claim is that routing is legible: which *provider* handles which role is declared in config and printed by `batonai config show`, but which *model* is a hidden inherited setting.

**Decision.** Ask at setup. `batonai init` — and the wizard's setup step, which is now where most projects get initialized (ADR-026) — offers a model choice per role that will actually run, and writes it into `.ai/config.yaml` as ordinary configuration.

- **"Use the CLI's default" stays an option and stays the default.** Choosing it writes nothing, so existing projects and anyone who presses Enter behave exactly as today. The point is to make the choice *visible and available*, not to force it.
- **Still pure configuration.** The answer lands in `.ai/config.yaml`; nothing is decided at runtime and ADR-004 is untouched. A user may edit or delete it afterwards like any other setting.
- **Per project, not per machine.** A throwaway experiment can run a cheap model while a production repo runs a strong one, without either touching the CLI's global config — which is the thing baton currently cannot influence at all.
- **Setup should say what the choice costs.** The reason this matters is quota (ADR-016's whole subject), so the prompt names the trade-off rather than listing opaque model ids.

**Trade-offs.** (a) Model identifiers change often and are vendor-specific; a hardcoded menu will age. Mitigation: offer a short list plus free text, and never validate against a fixed set — an unknown string is passed through to the CLI, which is the authority. (b) One more question in a setup flow ADR-026 deliberately kept short; it belongs behind the same "use defaults" fast path. (c) A pinned model can silently stop existing when a vendor retires it; the failure surfaces as a provider error at preflight, which is where provider problems already surface.

**Alternatives considered.** (a) Leave it to each CLI's own config — the status quo; rejected because it makes a decision with real cost consequences invisible and non-project-scoped. (b) Pin defaults in baton's own `defaults.yaml` — rejected: it would silently override what users configured in their CLIs, and baton has no business choosing a model on their behalf. (c) Show the resolved model in `batonai doctor`/`config show` without offering a choice — worth doing regardless, but it reports the problem rather than giving the user the lever.


## ADR-032 — `batonai setup`: the routing and model decisions stay revisable

**Status:** Accepted · 2026-07-28 · **Implemented 2026-07-28.**

**Context.** Two decisions dominate what a run costs and how good it is: **which provider handles which role** (ADR-016's quota-spread default — planner/reviewer on codex, coder on claude, designer on antigravity, publisher on opencode) and **which model each provider runs** (ADR-031). Both were reachable only at `init` time or by hand-editing YAML. The defaults are good, but they were chosen for one owner's plans and one machine's CLI configuration; a user on different subscriptions, or one who simply wants the Coder on codex for a project, had no supported way to say so after setup.

**Decision.** Add `batonai setup`: prints the current role → provider → model assignment, then asks about each, and writes the answers into `.ai/config.yaml`. **The ADR-016 defaults are unchanged and remain the default** — this only makes them visible and revisable.

- **Enter keeps everything.** A run with no changes writes nothing and says "nothing changed"; the file is not even touched.
- **Provider names are validated, model ids are not.** A provider must be one the registry actually knows, because a typo would otherwise surface much later as a preflight failure; model identifiers are vendor-specific and change often, so an unrecognised one is passed through to the CLI, which is the authority (ADR-031).
- **`-` clears a model pin** back to whatever that CLI is configured to use — baton's default posture, and the only way back once a model is pinned.
- **Merges, never overwrites.** The config is parsed, the two keys are updated, and the document is written back, so a user's `pipeline`, timeouts and `enabled` flags survive. It is re-serialised from the parsed document, so **comments are lost** — the command says so before writing rather than surprising anyone.
- Only roles with a real choice are offered: the zero-LLM tester (ADR-024) and the deterministic publisher floor (ADR-018) have no model to pick.

**Trade-offs.** (a) Losing comments in a hand-annotated `.ai/config.yaml` is a genuine cost; a comment-preserving round-trip needs a different YAML library, and the warning was judged sufficient for a file baton itself generates. (b) The provider list is whatever the registry reports, so a plugin (ADR-009) appears automatically — including one that makes no sense for a given role; role/provider compatibility is not modelled, and preflight remains the check that matters.

**Alternatives considered.** (a) Tell users to edit `.ai/config.yaml` — the status quo; it works, but it makes a first-class decision feel like an internal detail and gives no discoverable list of valid providers. (b) Ask everything during the wizard's setup step — rejected as scope creep on a flow ADR-026 deliberately kept to two questions; `init` now points at `batonai setup` instead. (c) A flag-driven `batonai config set roles.coder.provider=codex` — more scriptable, but it answers "how do I change it" only for someone who already knows what the options are.


## ADR-033 — Model suggestions are shared and live-discovered, not silently absent

**Status:** Accepted · 2026-07-29 · **Implemented 2026-07-29** (a same-day fix to ADR-031/032's live behaviour).

**Context.** A live user report: running `batonai init`, the `codex` model prompt showed nothing at all — no suggestions, no hint — while `claude`'s did (`opus/sonnet/haiku`). The user happened to already know a valid codex model id from their own `~/.codex/config.toml` and typed it; a user who didn't would have been stuck typing a guess, or pressing Enter and never learning a choice existed. Root cause: `init.py` and `setup.py` each carried their **own copy** of a `MODEL_SUGGESTIONS`/`MODEL_HINT` dict, both containing only a `claude` entry — the two commands had drifted, and `codex` had simply never been added to either.

Investigating further found a second real capability going unused: `agy` (the antigravity CLI) ships an `agy models` subcommand that prints its current, real model list — unlike codex or claude, which expose no such thing. Wiring that in gives genuinely live, always-current suggestions for the one provider that supports it, rather than a static guess that goes stale (exactly the failure ADR-031 designed the "no validation" rule around).

**Decision.** Extract a single shared module, `cli/model_catalog.py`, used by both `init` and `setup`.

- **One source of hints/suggestions**, so the two commands cannot drift again. `codex` and `opencode` (neither has a listable model set) now get an explanatory hint instead of silence — "no fixed list — check `~/.codex/config.toml`'s `model =` line…" — so a user without prior knowledge is told where to look rather than shown nothing.
- **Live discovery where a provider actually supports it.** `discover_models()` shells out to `agy models` and parses its plain output; on success, live suggestions are shown in place of any static list. This is best-effort by construction — a missing binary, timeout, non-zero exit, or empty output all yield no suggestions, never an error, exactly like every other optional shell-out in this codebase (`repowise health`, ADR-025).
- **Bounded, not a dump:** capped at 8 suggestions, matching the existing pattern for anything the user is meant to glance at, not read in full.

**A second bug found while verifying the fix, not in review.** `agy models` was live-tested twice with different results: with `stdin=/dev/null` it returned its list in ~2 s; left to inherit the calling process's ambient stdin (a real pty, not closed, not fed) it **hung indefinitely** until killed. `discover_models()`'s `subprocess.run` call did not set `stdin` at all — meaning it silently inherited whatever fd `init`/`setup` happened to have, which in a real interactive terminal session is exactly the hanging case. Fixed by passing `stdin=subprocess.DEVNULL` explicitly, so the child process never depends on the parent's stdin type. Re-verified afterward through an actual pty (`script`): the same call completed in 1.96 s. A test pins that `stdin=subprocess.DEVNULL` is always passed.

**Trade-offs.** (a) `agy models`' output format is not a documented contract — a future version could change or remove it, in which case `discover_models` simply returns nothing and the (still-present) static/hint fallback takes over; nothing breaks, the suggestion just reverts to what it is for codex today. (b) Every `setup`/`init` call that touches antigravity now costs up to ~2 s for the live query; judged worth it against showing a stale or absent list.

**Alternatives considered.** (a) Hardcode a codex model list — rejected on the same ADR-031 grounds that killed the idea originally: model ids change too often, and a hardcoded list would eventually mislead rather than help. (b) Leave `codex`/`opencode` with no suggestion, since neither has a machine list — rejected once the reporter's experience showed "nothing at all" reads as a gap, not a deliberate absence; a hint costs nothing and was missing purely by omission.


## ADR-034 — Hardening pass: no silent states

**Status:** Accepted · 2026-10-21 · **Implemented 2026-10-21.**

**Context.** A from-scratch review of the whole codebase (every module read, every suspicion reproduced before it was written down) found that the architecture and its guarantees held, but that several failure paths were *silent*: the tool kept working while quietly reporting something false, or quietly doing less than it claimed. Eight findings shared that shape, and they are recorded here as one decision because they were fixed under one principle — **a state baton cannot vouch for must be visible, never defaulted to "fine".**

1. **A crash left `run.json` saying `running` forever.** The engine's stage loop caught only `KeyboardInterrupt`; any other exception from a transport or a plugin adapter propagated with the run still marked RUNNING on disk. Worse, `batonai runs show` rendered that state through its success branch and printed "run succeeded". Reproduced by simulating a mid-Coder crash.
2. **Untracked files with spaces or non-ASCII names vanished from the captured diff.** `git status --porcelain` quotes such paths (`?? "my file.txt"`); the quoted string was passed to `git diff --no-index` as-is and silently produced nothing. The Reviewer never saw the file. Reproduced with a real repo.
3. **The "coder changed nothing" safety net was blind on `revise` and the fix-loop.** It compared the tree to HEAD; after a first pass the tree is already dirty, so every re-run read as "changed" — a Coder that did nothing on its second turn passed as a success.
4. **A timed-out provider's helper processes outlived the stage.** `proc.kill()` reached only the direct child; CLIs spawn MCP servers and node workers that kept running — and kept consuming quota — after baton had moved on or exited.
5. **One undecodable byte in a provider's output aborted the stage** (buffered path: an uncaught `UnicodeDecodeError`, which with finding 1 also left the run "running"; streaming path: the read loop stopped and the stage waited for the watchdog, then reported "timed out" for the wrong reason).
6. **Ctrl-C mid-stage inside the wizard printed "cancelled — nothing was changed."** The run directory existed, a stage was recorded FAILED, and the Coder may well have written files. Outside the wizard it was Click's bare "Aborted!" with no summary and exit 1 — indistinguishable from a stage failure.
7. **`batonai publish` reused the latest run's drafted commit message unconditionally** — including after the user had edited further, or when the newest run was unrelated to the current changes. The source label said "run <id>", but a plausible-looking message describing the wrong diff is exactly the kind of thing one does not re-read.
8. **The Coder could not do what its prompt asked.** `claude -p --permission-mode acceptEdits` auto-approves file edits but denies every Bash call in headless mode, so "verify what you build (run the tests)" silently failed on every run. The Reviewer, in codex's `read-only` sandbox, may likewise be unable to run a test suite that writes caches — and was given no instruction on what to do about it.

**Decision.**

- **Every abnormal exit is recorded before it propagates.** The stage loop now has a generic `except Exception` beside the `KeyboardInterrupt` one; both route through one `_abort_stage` that marks the stage and the run FAILED, saves, and logs — then re-raises. A run can no longer be left RUNNING by a crash. `render_run_summary` and `runs list` gained an explicit RUNNING rendering ("run not finished … `batonai resume`"), so the one remaining way to see that state — another baton process genuinely mid-run, or a `kill -9` — is named for what it is and never shown as a success.
- **Change detection compares against a pre-stage baseline, not HEAD.** Before an edit-stage runs, the engine snapshots the working-tree diff; afterwards "changed" means *the diff is not byte-identical to that baseline*. On a clean tree this is exactly the old behaviour; on a dirty tree (revise, fix-loop, or a user who ignored the warning) it is the first time the check has worked at all. The Reviewer still receives the cumulative working-tree diff — reviewing the whole feature is the point of a re-review — only the yes/no "did this stage do anything" question is stage-scoped. The `CHANGE_STATUS: no_changes_needed` marker (ADR-021) keeps its meaning. The fake provider gained an `[[append:…]]` directive because its tests had, unknowingly, relied on the blind spot: the fix-loop test's second pass rewrote the same bytes.
- **Working-tree status is read with `-z`.** `git status --porcelain -z -uall` yields NUL-separated, unquoted paths; a small parser handles the rename/copy records that carry a second field. The deterministic Publisher floor (ADR-018) switched to the same command, which fixes its own long-documented gap for free: it now sees new files, and labels each path added/modified/deleted/renamed.
- **Children run in their own session and die as a tree.** The transport starts every provider with `start_new_session=True` and kills with `os.killpg` on timeout. Because a new session leaves the terminal's foreground group, the child no longer receives the terminal's SIGINT on its own — so the transport now catches `BaseException` around the wait, kills the tree, and re-raises. Both paths decode with `errors="replace"`: a stray byte becomes U+FFFD in the log, not a dead stage. The buffered path moved from `subprocess.run` to `Popen`+`communicate` to make all of this possible with one code path for process creation.
- **Ctrl-C mid-stage ends with the run summary and exit 130.** `run`/`resume`/`revise` share one driver (`cli/commands/_shared.py`, which also removed three drifting copies of the same prelude and epilogue). It catches the `KeyboardInterrupt` the engine re-raises *after* recording the stage as FAILED, renders the summary — which names the interrupted stage and the `resume` command — adds one line saying that files the Coder already wrote are still in the tree, and exits 130. The wizard's "nothing was changed" message is now only reachable from a prompt, where it is true.
- **A run's commit draft is reused only while the tree still matches.** `publish` compares the run's recorded `diff.patch` with the current working-tree diff; on a mismatch it says so in one dim line and drafts afresh. The fresh draft is built from the same tracked+untracked capture the Reviewer gets, not from `git diff HEAD` (which again missed new files). The draft's source moved from a Rich panel subtitle — which was clipped to the panel's width, hiding it behind any one-line message — to its own line.
- **Command access for the Coder is an explicit, bounded opt-in.** `providers: {claude: {allow_commands: true}}` adds `--allowedTools Bash` *together with* a `--disallowedTools` list that keeps `git commit/push/reset/checkout/switch/restore/stash/rebase/merge/tag/branch/clean` and every `gh` command out of reach — disallowed rules take precedence in Claude Code, so ADR-014's "no stage ever commits" now holds mechanically where it used to hold by instruction alone (acceptEdits had made git commands impossible by accident, not by design). Codex's `workspace-write` sandbox already permits commands and blocks the network, so the flag is a documented no-op there. It is **off by default**: ADR-007's trust model is unchanged for anyone who does not turn it on. Independently, the Coder prompt now says what to do when commands are denied (state it under *How to verify*, list the commands a human should run) and the Reviewer prompt says what to do when a check cannot run (say so; never report a check that did not happen) — so the gap is at least no longer silent in the artifacts.
- **Smaller items fixed under the same principle:** the verdict regex is case-insensitive and normalised (a lowercase "needs work" now triggers the fix-loop); a non-object JSON reply from claude is a failed result, not an `AttributeError`; the argv rewrite derives the command set from Typer instead of a hand-kept list (a forgotten entry turned `batonai <newcmd>` into a pipeline run); config warnings print as one tidy CLI line instead of Python's `path.py:274: UserWarning:`; two user-facing strings still said `ai` (the pre-ADR-026 binary name); the wizard's "Publish (commit)" menu item now says what it does (preview); an empty revise correction is rejected instead of sent; `init`'s starter config lists all six roles and the real default stage order.

**Trade-offs.** (a) `start_new_session` means a provider CLI that *expected* to share the terminal's process group — for example to detect Ctrl-C itself and clean up gracefully — now gets SIGKILL from baton instead. Headless `-p`/`exec` modes have no such cleanup to lose; the engine already persisted everything before the kill. (b) The baseline snapshot adds one `git status`+`git diff` per edit-stage (tens of milliseconds). (c) `allow_commands` is a blocklist, and blocklists are never complete: a Coder with it on could still run `rm -rf` inside the project directory — which is the trust ADR-007 already grants it through file edits. What the list guarantees is narrower and exact: no git history, no remote. (d) Stage-scoped change detection makes the fake provider's "write the same bytes again" pattern a failure, which is correct but means test authors must mean *change* when they say change.

**Alternatives considered.** (a) Stashing the dirty tree before an edit-stage to get a clean stage-only diff — rejected: baton must never mutate the user's index or tree (ADR-007). (b) `--permission-mode bypassPermissions` for the Coder — rejected: it also removes the one mechanical barrier to `git commit`/`push`, and ADR-014 is a guarantee, not a preference. (c) Deleting the "running" state's rendering problem by writing a PID file and detecting liveness — over-engineering for a state that, after the generic exception guard, only a `kill -9` can produce. (d) Keeping three copies of the pipeline-command prelude and fixing Ctrl-C in each — rejected; the copies had already diverged, and the fix needed to be identical.
