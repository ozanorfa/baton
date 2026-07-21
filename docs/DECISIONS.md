# Architectural Decision Records — AI Coding Orchestrator

**Status:** Living · 21 ADRs · updated 2026-07-21
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

**Status:** Accepted · 2026-07-21

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

**Trade-offs.** (a) `git add -A` can stage unrelated working-tree changes — mitigated by showing the file list before the confirmation (the owner chose this over "tracked-only" or "no auto-stage"). (b) Reusing the latest run's `commit_message.md` can be stale if the tree changed since that run — mitigated because the draft is always shown before committing and `-m` overrides it. (c) The commit message keeps only the commit section when the draft also embeds a "PR description" heading (a simple split, with the whole text as fallback).

**Alternatives considered.** Letting the Publisher role commit when enabled (rejected — breaks ADR-014 and the owner's "no automatic git" requirement). `--push` without confirmation (rejected — the owner is git-cautious; confirmation is the default, `--yes` opts out).

---

## ADR-021 — A declared no-op is a success, not a silent-permission-block failure

**Status:** Accepted · 2026-07-21

**Context.** ADR-007's safety net: because a permission-blocked headless run reports success at the protocol level (claude.py `permission_block.json`), the engine treats an edit-stage that returns success **but changes nothing** as a failure — the workspace is the only honest witness. This correctly catches silent blocks, but it also mislabels a **legitimate no-op**: "add a license header if missing" when the header is already there is a real, correct outcome with zero changes, yet it was failing the run.

**Decision.** Distinguish the two with an explicit, low-ceremony signal. The Coder template (`prompts/coder.md`) instructs: if no change is genuinely needed, make no edits and put exactly `CHANGE_STATUS: no_changes_needed` as the first line of the summary. The engine (`core/engine.py`), on zero workspace change, checks `result.text` for that marker (`NO_CHANGES_MARKER`): present → the stage **succeeds** with an empty diff and a `stage_no_changes` event; absent → the existing failure fires unchanged.

**Why it's safe — no regression is possible.** Absent marker + zero change behaves **exactly as today** (failure), so the permission-block detection is fully preserved. The marker only ever *relaxes a false negative*. If the model forgets to emit it on a true no-op, the result is the current behavior (a false failure) — never a false success. So a silent permission block can never be mistaken for a no-op: the block produces no marker.

**Trade-offs.** (a) The marker is a prompt convention, so it shares the fragility of any model-emitted token — mitigated entirely by the fail-safe direction (forgetting it fails safe). (b) A downstream stage (Reviewer) then sees no `diff.patch`; the contract admits it but `inputs_section` simply omits an absent artifact, so the Reviewer reviews the "nothing changed" situation cleanly.

**Alternatives considered.** (a) A structured `CHANGE_STATUS:` enum with `changed`/`no_changes_needed`/`blocked` (the original suggestion) — rejected as over-built: only the no-op case needs rescuing, and a `blocked` self-report can't be trusted (a blocked provider won't reliably say so). (b) Always trust protocol success and drop the workspace check — rejected: it throws away the only real permission-block detector.
