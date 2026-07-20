# Ideas — parked for later implementation

Not decisions (those go in [DECISIONS.md](DECISIONS.md)); this is a holding pen for evaluated ideas we may build. Each entry records the conclusion *and the reasoning*, so a future session doesn't have to redo the evaluation.

## 2026-07-17 · Cutting paid-token usage without a local LLM

**Context:** the pipeline's shallow tasks (Publisher, `ai ask`) burn paid quota on work that doesn't need a frontier model. User rules out local LLMs (no Ollama). Evaluated: opencode, aider, repowise.

### 1. opencode adapter for shallow roles — PICKED over aider

- Add `opencode.py` next to the existing adapters in `src/ai_orchestrator/providers/`; `opencode run "<prompt>"` is non-interactive and scriptable, nearly identical in shape to the `claude.py`/`codex.py` subprocess pattern.
- opencode never touches git on its own → the ADR-014 "orchestrator never commits" guarantee holds by construction.
- Wire via existing per-role provider config (`.ai/config.yaml` `providers:`) — no new orchestration logic. Default it for **Publisher** and `ai ask`; never for Coder/Reviewer.
- **aider rejected** for this use: designed to edit code and auto-commit (fights ADR-014 unless disabled), heavyweight for text drafting.

**The "free" caveat (important):** opencode is a free *client*; the model still comes from somewhere. Non-local free options: OpenRouter `:free` models, Google AI Studio free-tier API key (the API — separate from the dead personal Gemini CLI, may still work), occasional promo models in opencode. All rate-limited, and free tiers typically may train on submitted data — fine for commit messages, think twice before pointing at proprietary code.

### 2. Repowise as a context source (token *reducer*, not a provider)

<https://github.com/repowise-dev/repowise> — codebase-intelligence MCP server + CLI (tree-sitter dependency graph, git analytics, health scores, auto-generated wiki). AGPL-3.0; index-only mode needs **zero LLM calls/keys**.

- It doesn't replace any pipeline stage; it attacks the *biggest* cost in every run: per-stage repo re-exploration overhead. Stages get distilled context (via its MCP server or `repowise distill` output injected through the existing context system, extending ADR-013's docs index) instead of exploring from scratch.
- Fits the post-MVP roadmap: MCP support is already planned.
- **Timing honesty — when is it worth it?** Its intelligence is *derived from* an existing codebase and git history. On a brand-new project it starts near-empty — ADR-013's greenfield propose-structure guidance is doing the "help the agent start" job there, not repowise. Its value ramps up with the project: the wiki/index build incrementally per commit, so initializing it early on a new project is cheap and pays off from roughly the point the repo is big enough that agents would otherwise re-explore it every run. For *established* projects (the charm_website case), value is immediate.
- Complements, not duplicates, ADR-015 session chaining: chaining avoids re-exploration *within* a run's same-provider chain; repowise cuts it for cold starts and cross-provider stages too.

### 3. Zero-LLM Publisher fallback — the floor

Deterministic commit-message generation from the diff (conventional-commits template: changed paths → scope, diffstat → summary). No model, no quota, no rate limit. Keep as fallback for when the free tier is throttled — or even as the default for trivial diffs.

### Suggested build order (when picked up)

1. opencode adapter + route Publisher/`ask` to it (smallest change, immediate quota relief on paid pools).
2. Zero-LLM fallback (tiny, pure Python).
3. Repowise integration (largest; gate on MCP support landing in the roadmap).
