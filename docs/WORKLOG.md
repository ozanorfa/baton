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
