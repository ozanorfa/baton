# Work Log — AI Coding Orchestrator

Running log of all work sessions: what was done, by whom (👤 user / 🤖 Claude), problems hit, and how they were resolved. Newest entries at the bottom. Git history covers the code; this covers everything else.

---

## 2026-07-11 · Session 1 — Phase 1 documentation

- 👤 Provided the full project specification (deterministic multi-CLI orchestrator, Planner/Designer/Coder/Reviewer roles, tmux, CAO evaluation request).
- 🤖 Researched Amazon CAO (awslabs/cli-agent-orchestrator). Verdict: not a foundation (agent-driven supervisor model, heavyweight FastAPI/SQLite runtime, coordination costs tokens); borrow its tmux/adapter patterns later.
- 👤 Approved two deviations from the original spec:
  - **Headless-first transport** instead of tmux scraping (`claude -p --output-format json`, `codex exec`, `gemini -p`); tmux deferred to post-MVP observability (ADR-002).
  - **Codex CLI** as the OpenAI provider vehicle for Planner/Reviewer (ADR-003).
- 🤖 Wrote the six design docs, reviewed one at a time by user: IMPLEMENTATION_PLAN, ARCHITECTURE, DECISIONS (11 ADRs), PROJECT_STRUCTURE, TASKS (35 tasks, ~36 h), MVP. Consistency pass found and fixed one drift (missing `diff.patch` in ARCHITECTURE's run-dir tree).
- 👤 Approved all docs; gave go for implementation.

## 2026-07-11 · Session 1 — Milestone M0: Foundations (T01–T07)

- 🤖 T01: git init, uv project (`src/` layout), `ai` console script, pytest+ruff. Python 3.13.2 via uv (spec: ≥3.12).
- 🤖 T02: shared pydantic models (`core/models.py`) — stage/run state machines, AgentRequest/Result, Usage (None = unmeasured, never estimated).
- 🤖 T03: config schema + `defaults.yaml`; cross-checks (stage→role, role→provider) fail at load time; unknown keys warn.
- 🤖 T04: config loader — precedence CLI > env (`AI_ORCH_*`) > project > user > defaults; every value tracks its source; validation errors name the offending file.
- 🤖 T05: `ai config show` with source column. Deviation: source labels shortened to `project`/`user` (full paths listed below table) because long paths wrapped the Rich table badly.
- 🤖 T06: RunManager — atomic `run.json` writes (temp+rename); crash-at-rename test proves prior state survives.
- 🤖 T07: JSONL event log per run.
- ✅ **M0 demo passed:** `ai --version`, `ai config show` with live source annotation. 29 tests green, ruff clean, one commit per task (7 commits).

## 2026-07-11 · Session 1 — Provider CLI setup (prep for M1)

- 🤖 Found only Claude Code installed; `codex` and `gemini` missing.
- 👤 Installed both via npm — hit `command not found`: npm's global bin (`~/npm/bin`) was not on PATH (longstanding; `firebase`/`tsc` in there were also unreachable).
- 🤖 Was correctly permission-blocked from editing `~/.zshrc`; provided the fix for user to run. Recommended the **append** variant (`export PATH="$PATH:$HOME/npm/bin"`) so npm's bundled `node`/`npm` don't shadow system ones.
- 👤 Fixed PATH, ran `codex login` — **Codex authenticated ✅** (codex-cli 0.144.1).
- 👤 `gemini` login failed: *"This client is no longer supported for Gemini Code Assist for individuals → migrate to Antigravity"*.
- 🤖 Researched: **Google shut down Gemini CLI for personal accounts on 2026-06-18** (moved individuals to Antigravity CLI / paid API keys). User's old `~/.antigravity` symlinks are broken (IDE uninstalled). → **Designer-provider decision pending** (Antigravity CLI vs. paid API key vs. defer Designer role). Designer stage is optional & disabled by default, so MVP is not blocked.
- 👤 Asked for this work log; 🤖 created it and will append every session.
- 👤 Decided: **install Antigravity CLI** as the Designer provider (rather than paid Gemini API key or deferring the role).
- 🤖 Wrote **ADR-012** (Antigravity CLI replaces Gemini CLI); propagated the change across all six docs, `defaults.yaml` (provider `antigravity`, command `agy`), and tests. First real exercise of the provider-agnosticism goal: zero core-design changes needed.
- ⏳ Pending (user): install Antigravity CLI + sign in, then M1 starts.

## 2026-07-11 · Session 1 — Milestone M1: Provider Adapter Layer (T08–T15)

- 👤 Installed Antigravity CLI (`curl -fsSL https://antigravity.google/cli/install.sh | bash` → `agy` 1.1.1 in `~/.local/bin`) and signed in with Google — **Antigravity authenticated ✅**. All three providers now live: claude 2.1.207, codex 0.144.1, agy 1.1.1.
- 🤖 Starting M1: transport layer (T08), adapter ABC + registry (T09), three concrete adapters with recorded fixtures (T10–T12), plugin discovery (T13), `ai doctor` (T14), `ai ask` (T15).
- 🤖 T08–T09: headless transport (stdin prompts, structured timeout/missing-binary results) + `ProviderAdapter` ABC with registry. Adapters are pure (build/parse only, never spawn) → contract-testable against recorded fixtures.
- 🤖 T10 (ClaudeCodeAdapter): captured real fixtures from claude 2.1.207. **Field finding:** a permission-blocked headless run exits 0 with `is_error: false` — protocol-invisible; only a stage-level `git diff` check can catch it (validates ADR-007/T26 design).
- 🤖 T11 (CodexAdapter): captured real fixtures from codex-cli 0.144.1. **Better than expected:** `--json` JSONL carries thread_id (resumable) AND measured token usage; `-s read-only|workspace-write` sandbox maps directly to role write-access.
- 🤖 T12 (AntigravityAdapter): captured real fixtures from agy 1.1.1. **Field findings:** (1) no stdin prompt support — `-` taken literally → ADR-010 amended with an argv exception; (2) `--sandbox` is incompatible with print mode (exit 1) — never passed; (3) no session id or token usage in print mode → honest `None`s; (4) `--print-timeout` (default 5m) pinned to request timeout.
- 🤖 T13: entry-point plugin discovery, integration-tested against a real (unmocked) dist-info on sys.path; broken plugins warn and are skipped.
- 🤖 T14: `ai doctor` — live run shows all three providers healthy with role bindings (claude 2.1.207/coder, codex 0.144.1/planner+reviewer, agy 1.1.1/designer).
- 🤖 T15: `ai ask --role <role>` — first sanctioned token spend. Live round-trips through all three providers succeeded; usage line shows measured tokens/cost/session where available, nothing where not.
- ✅ **M1 complete:** 65 tests green (unit + contract + integration), one commit per task. Real fixtures recorded from all three CLIs.
- 👤 Asked for a persistent manual-testing reference; 🤖 created `docs/MANUAL_TESTING.md` (grows per milestone). Also clarified: the orchestrator is a general base, not Flutter-specific — Flutter enters via per-project context (`.ai/project.md`) and role prompt templates.

## 2026-07-11 · Session 1 — Milestone M2: Pipeline Engine (T16–T20)

- 👤 Confirmed the orchestrator must stay usable beyond Flutter (web/backend); gave go for M2.
- 🤖 Starting M2: routing engine (T16), pipeline engine (T17), fake provider harness (T18), two-stage integration test (T19), `ai "<request>"` wiring (T20).
- 🤖 T16: RoutingEngine — all stages resolved + every distinct active provider health-checked before stage 1; disabled stages' providers not checked.
- 🤖 T17: PipelineEngine — sequential fail-stop loop; every transition persisted before the next action; prompts and raw stdout/stderr saved per stage; JSONL events.
- 🤖 T18+T19: fake provider CLI (prompt-directive driven: `[[fail:…]]`, `[[sleep:N]]`, `[[output:…]]`) + adapter discovered via committed dist-info through the real entry-point mechanism; full-stack two-stage integration tests incl. failure variant — zero tokens.
- 🤖 T20: bare `ai "<request>"` (argv rewrite → `ai run`), `--with-designer`, dirty-git-tree warning, live per-stage progress, summary table with measured tokens.
- ✅ **M2 demo (real providers):** two-stage pipeline in a scratch repo — Codex planned (7s, 25.9k/171 tokens), Claude Code created `hello.py` (22s, 42.9k/519 tokens), file verified working. **Field finding:** the Planner attempted to create the file itself and was stopped only by its read-only sandbox — M2's naive prompt has no role boundaries; exactly what M3's role templates (T21) exist to fix.
- ✅ **M2 complete:** 82 tests green. MANUAL_TESTING.md updated with M2 commands.
