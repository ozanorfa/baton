# Ideas — parked for later implementation

Not decisions (those go in [DECISIONS.md](DECISIONS.md)); this is a holding pen for evaluated ideas we may build. Each entry records the conclusion *and the reasoning*, so a future session doesn't have to redo the evaluation.

## 2026-07-17 · Cutting paid-token usage without a local LLM

**Context:** the pipeline's shallow tasks (Publisher, `ai ask`) burn paid quota on work that doesn't need a frontier model. User rules out local LLMs (no Ollama). Evaluated: opencode, aider, repowise.

### 1. opencode adapter for shallow roles — PICKED over aider — ✅ SHIPPED 2026-07-21 (ADR-017)

Graduated out of this holding pen. Implemented as `src/ai_orchestrator/providers/opencode.py`, verified against opencode 1.18.4, Publisher's default provider; `ai ask --role publisher` inherits it. Reasoning and the shallow-text-only guardrail now live in **[DECISIONS.md → ADR-017](DECISIONS.md)**. Original notes kept below for the record:

- `opencode run -- "<prompt>"` is non-interactive and scriptable, nearly identical in shape to the `antigravity.py` subprocess pattern (prompt in argv, not stdin).
- opencode never touches git on its own → the ADR-014 "orchestrator never commits" guarantee holds by construction.
- Wired via existing per-role provider config — no new orchestration logic. Publisher + `ai ask`; never Coder/Reviewer.
- **aider rejected** for this use: designed to edit code and auto-commit (fights ADR-014 unless disabled), heavyweight for text drafting.

**The "free" caveat (important):** opencode is a free *client*; the model still comes from somewhere. Non-local free options: OpenRouter `:free` models, Google AI Studio free-tier API key (the API — separate from the dead personal Gemini CLI, may still work), occasional promo models in opencode. All rate-limited, and free tiers typically may train on submitted data — fine for commit messages, think twice before pointing at proprietary code. (Handled in ADR-017 by confining opencode to shallow text.)

### 2. Repowise as a context source (token *reducer*, not a provider)

<https://github.com/repowise-dev/repowise> — codebase-intelligence MCP server + CLI (tree-sitter dependency graph, git analytics, health scores, auto-generated wiki). AGPL-3.0; index-only mode needs **zero LLM calls/keys**.

- It doesn't replace any pipeline stage; it attacks the *biggest* cost in every run: per-stage repo re-exploration overhead.
- **Timing honesty — when is it worth it?** Its intelligence is *derived from* an existing codebase and git history. On a brand-new project it starts near-empty — ADR-013's greenfield propose-structure guidance is doing the "help the agent start" job there, not repowise. Value ramps up with the project; for *established* projects it'd be immediate — **if** it composed with baton, which it currently doesn't (see below).
- Complements, not duplicates, ADR-015 session chaining: chaining avoids re-exploration *within* a run's same-provider chain; repowise would cut it for cold starts and cross-provider stages too, in principle.

**2026-07-23 — re-evaluated with a live install (v0.34.0), original notes above were partly wrong:**

- `repowise distill <cmd>` is **not** a repo-summary command — it compresses the output of an arbitrary command you run through it (e.g. `repowise distill pytest`), errors-first, reversible. The rich per-repo interface (`get_overview`, `get_context`, `get_risk`, …) is **ten MCP tool functions**, reachable only via `repowise serve` + an MCP client. baton has none (ARCHITECTURE.md §7.2 is still "Future") — this is the one part of the original note that held up: real repowise value is MCP-shaped, full stop.
- Tested whether the offline path (`repowise init --index-only -y`, genuinely zero LLM calls/no key) gives a "free" win through baton's *existing* docs-index (`context/awareness.py`, already reads root `CLAUDE.md`/`AGENTS.md`) without any MCP client. **It doesn't compose:** index-only mode writes its summary to **`.claude/CLAUDE.md`** (Claude Code's own project-settings path), not repo-root `CLAUDE.md`, and generates no `AGENTS.md` at all. `docs_index()` only scans the project root and `docs/` — never `.claude/` — so baton would never see the file. Even if it did: the generated text instructs the reader to call `get_answer`/`get_context`/etc., tools that don't exist without a live repowise MCP session — injecting it into a headless one-shot provider prompt (what every baton adapter does) would tell the model to use tools it structurally cannot call. There is no zero-code path here.
- **Real footgun found during the live test, independent of baton:** `repowise init -y` reached *outside* the target repo and registered itself as a global MCP server + `PostToolUse`/`SessionStart` hooks in the tester's own `~/.claude/settings.json` and Claude Desktop's `claude_desktop_config.json` — not scoped to the repo being indexed. Reverted by hand (no built-in undo observed). **Anyone trying repowise standalone should know `-y` has machine-wide side effects, not just repo-local ones** — worth a caution independent of whether baton ever integrates it.
- **Constraint for whenever real MCP-client support lands and this gets picked back up:** per user direction, repowise must never run against a greenfield project (mirrors ADR-013's existing established/greenfield split — a fresh repo's index is near-empty anyway) and, on an established project, must be a deliberate **one-time** setup step the user triggers — never something baton re-invokes automatically on every run.

**2026-07-23, correction to the above (same day) — the MCP-only conclusion was too strong.** User pointed out baton already shells out to plain CLIs for everything else (claude/codex/opencode/testrunner/deterministic) — why not repowise's own plain CLI subcommands the same way? Right: alongside the ten MCP-only tool functions, repowise also has ordinary terminal commands that need no MCP client and no LLM — `repowise health`, `repowise risk`, `repowise dead-code`, `repowise search`, `repowise status` — offline, stdout, scriptable, exactly the shape of the existing provider pattern. This reopens a real, buildable, non-MCP path:

- A new context source (not a provider/role) that shells out to a cheap read command (e.g. `repowise health`/`status`) **only if `.repowise/` already exists** in the project — i.e. only if the user already ran `repowise init` themselves at some point. If `.repowise/` is absent, skip entirely, no dependency required.
- This one existence check *is* the constraint from the bullet above, for free: a greenfield project has no `.repowise/` (nothing indexed yet, so it naturally never triggers); an established project only gets it once the user has deliberately opted in by running `init` themselves. Baton would never call `repowise init` itself — that's the exact command that caused the global-config footgun above, so it must stay a human-triggered, outside-baton step, always.
- Not yet scoped or verified live (need to check real `repowise health`/`status` output size/format before designing the injection, same as every other provider probe in this project). Parked here until picked up.

- **Conclusion:** the MCP-tool interface stays blocked on the MCP-client roadmap item, same as before. But a smaller, real, non-MCP path (plain CLI health/status output, gated on a pre-existing `.repowise/`) is open and buildable without it — this is now the more promising near-term angle if repowise gets picked up again, ahead of the full MCP-client work.

### 3. Zero-LLM Publisher fallback — the floor — ✅ SHIPPED 2026-07-21 (ADR-018)

Graduated. Implemented as the `deterministic` provider (`src/ai_orchestrator/providers/deterministic.py`); select per project with `roles: {publisher: {provider: deterministic}}`. Conventional-commit message from `git diff HEAD --stat`: changed paths → scope, diffstat → summary; type inferred only where unambiguous (docs/test/chore). No model, no quota, no rate limit. Reasoning and the untracked-files trade-off in **[DECISIONS.md → ADR-018](DECISIONS.md)**. The auto-fallback-on-throttle variant was deferred (needs engine retry plumbing); per-project selection ships the value now.

### Suggested build order (when picked up)

1. ~~opencode adapter + route Publisher/`ask` to it~~ — ✅ SHIPPED (ADR-017).
2. ~~Zero-LLM fallback (tiny, pure Python)~~ — ✅ SHIPPED (ADR-018).
3. Repowise integration — **re-evaluated 2026-07-23**: the full MCP-tool interface is still blocked on baton getting an MCP client (its own separate roadmap item). But a smaller non-MCP path opened up: plain `repowise health`/`status` CLI output, gated on the project already having a user-created `.repowise/` index (baton never runs `repowise init` itself). Not started — needs a live probe of the actual command output first. See corrected notes above.
